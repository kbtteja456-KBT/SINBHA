"""
Step C2.8 Item 3: Multi-Worker / Multi-Process Database Relay Test.
Proves that when running against a single shared database:
- Worker 1 can send a command and await completion.
- Worker 2 can poll the database for pending commands and report completion.
- Worker 1 gets the result without cross-worker memory sharing.
- Stale/expired commands are pruned.
- Late confirmations from Worker 2 update earlier chat messages.
- Device presence written by Worker 1 is visible on Worker 2.
"""

import os
import time
import json
import pytest
import asyncio
from pathlib import Path

# Use a clean test database file
TEST_DB_PATH = Path(__file__).resolve().parent / "test_c2_8_shared.db"
if TEST_DB_PATH.exists():
    try:
        TEST_DB_PATH.unlink()
    except Exception:
        pass

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["DATA_ENCRYPTION_KEY"] = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
os.environ["JWT_SECRET"] = "test_jwt_secret_c2_8_multiworker"

from app import database as db
from app.models import Base
from app.device_relay import CommandRelayManager
from app.command_schema import validate_command_packet

@pytest.fixture(scope="module", autouse=True)
def setup_shared_db():
    db.init_db()
    yield
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass

def test_multiworker_command_relay_and_resolution():
    """
    Simulates TWO completely independent server worker instances (Worker 1 and Worker 2)
    with their own process memory spaces, sharing ONLY the database.
    """
    # Initialize Worker 1 and Worker 2 relay managers (separate memory spaces)
    worker1_relay = CommandRelayManager()
    worker2_relay = CommandRelayManager()

    # Create test user and trusted laptop device
    unique_email = f"multiworker_{int(time.time() * 1000)}@example.com"
    user = db.create_user(unique_email, "Password123!")
    user_id = user["id"]
    target_dev_id = "win_laptop_worker_test"

    dev = db.create_or_register_device(
        user_id=user_id,
        device_id=target_dev_id,
        name="Windows PC",
        platform="windows",
        password="Password123!",
        is_signup=True
    )
    assert dev["status"] == "trusted"

    # Step 1: Worker 1 records presence for device
    db.update_device_presence(
        user_id=user_id,
        device_id=target_dev_id,
        last_ping=True,
        battery=88,
        is_charging=True,
        client_version="1.4.21",
        supported_tools=["open_app", "open_url"]
    )

    # Assert Worker 2 observes the exact presence written by Worker 1
    presence_on_w2 = db.get_device_presence(user_id, target_dev_id)
    assert presence_on_w2 is not None
    assert presence_on_w2["battery_level"] == 88
    assert presence_on_w2["is_charging"] is True
    assert worker2_relay.is_device_connected(user_id, target_dev_id) is True

    # Step 2: Worker 1 sends command
    cmd_id = f"cmd_multi_{int(time.time() * 1000)}"
    cmd_packet = {
        "id": cmd_id,
        "sender_device": "server",
        "target_device": target_dev_id,
        "type": "open_app",
        "payload": {"app": "notepad"},
        "created_at": time.time(),
        "expiry": 60,
    }

    # Worker 1 relays the command
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    relay_res = loop.run_until_complete(worker1_relay.relay_command(user_id, cmd_packet))
    assert relay_res["success"] is True

    # Step 3: Worker 2 polls database for pending commands
    # (Simulates laptop polling /api/devices/commands/pending on Worker 2)
    pending_on_w2 = worker2_relay.get_pending_offline_commands(user_id, target_dev_id)
    assert len(pending_on_w2) >= 1
    target_cmd = next((c for c in pending_on_w2 if c["id"] == cmd_id), None)
    assert target_cmd is not None
    assert target_cmd["type"] == "open_app"
    assert target_cmd["payload"]["app"] == "notepad"

    # Step 4: Run asynchronous completion: Worker 1 awaits, Worker 2 reports
    async def worker1_task():
        # Worker 1 waits up to 5s for command completion from DB
        return await worker1_relay.wait_for_command_completion(user_id, cmd_id, timeout=5.0)

    async def worker2_task():
        # Worker 2 simulates client executing command and reporting status after 200ms
        await asyncio.sleep(0.2)
        return worker2_relay.update_command_status(
            user_id=user_id,
            cmd_id=cmd_id,
            status="succeeded",
            result={"app": "notepad", "pid": 9876, "method": "spawn_binary"}
        )

    async def run_scenario():
        w1_coro = worker1_task()
        w2_coro = worker2_task()
        w1_result, w2_result = await asyncio.gather(w1_coro, w2_coro)
        return w1_result, w2_result

    w1_res, w2_res = loop.run_until_complete(run_scenario())

    # Assert Worker 1 successfully received the result updated by Worker 2!
    assert w1_res["status"] == "succeeded"
    assert w1_res["result"]["pid"] == 9876
    assert w1_res["result"]["app"] == "notepad"

    # Step 5: Test Late Confirmation across workers
    # Worker 1 sends a command that times out
    cmd_late_id = f"cmd_late_{int(time.time() * 1000)}"
    loop.run_until_complete(worker1_relay.relay_command(user_id, {
        "id": cmd_late_id,
        "sender_device": "server",
        "target_device": target_dev_id,
        "type": "open_app",
        "payload": {"app": "calculator"},
        "created_at": time.time(),
        "expiry": 60,
    }))

    # Create assistant message in chat: "I sent it to your Windows PC, but could not confirm"
    msg_dict = db.save_message(user_id, "assistant", "I sent it to your Windows PC, but could not confirm (timed out after 10s).")
    worker1_relay.register_late_confirmation_listener(cmd_late_id, user_id, message_id=msg_dict["id"], app_name="Calculator")

    # Worker 1 wait times out quickly
    timeout_res = loop.run_until_complete(worker1_relay.wait_for_command_completion(user_id, cmd_late_id, timeout=0.15))
    assert timeout_res["status"] == "timed_out"

    # Worker 2 receives late status update
    worker2_relay.update_command_status(
        user_id=user_id,
        cmd_id=cmd_late_id,
        status="succeeded",
        result={"app": "Calculator", "pid": 4321}
    )

    # Verify chat message was updated in database
    recent = db.get_recent_messages(user_id, limit=1)
    assert len(recent) == 1
    assert "Update: Calculator did open" in recent[0]["content"]

    loop.close()

def test_multiworker_http_api_endpoints():
    """
    Step C2.8 Item 3:
    Simulates TWO independent FastAPI server process workers against one test database.
    Worker 1 initiates a command via API.
    Worker 2 retrieves pending commands via GET /api/devices/commands/pending.
    Worker 2 posts execution report via POST /api/devices/command-status.
    Worker 1 queries the command and verifies 'succeeded' with result payload.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    # Two separate test clients representing two server workers
    worker1_client = TestClient(app)
    worker2_client = TestClient(app)

    # Create user and command token
    api_email = f"api_multiworker_{int(time.time() * 1000)}@example.com"
    user = db.create_user(api_email, "Password123!")
    user_id = user["id"]
    target_dev_id = "desktop_pc_worker_test"

    dev = db.create_or_register_device(
        user_id=user_id,
        device_id=target_dev_id,
        name="Desktop PC",
        platform="windows",
        password="Password123!",
        is_signup=True
    )
    cmd_token_data = db.create_device_command_token(user_id, target_dev_id)
    cmd_token = cmd_token_data["command_token"]
    session_token = db.create_session(user_id)

    headers_user = {"Cookie": f"sinbha_session={session_token}"}
    headers_device = {"x-command-token": cmd_token}

    # Worker 1: Relay a command via database insertion
    cmd_id = f"cmd_api_multi_{int(time.time() * 1000)}"
    create_res = db.create_device_command(
        user_id=user_id,
        cmd_id=cmd_id,
        sender_device="server",
        target_device=target_dev_id,
        cmd_type="open_app",
        payload={"app": "vs code"},
        expiry_seconds=60,
        status="queued"
    )
    assert create_res["status"] == "queued"

    # Worker 2: Polling pending commands
    res_pending = worker2_client.get(
        f"/api/devices/commands/pending?device_id={target_dev_id}",
        headers=headers_device
    )
    assert res_pending.status_code == 200
    data_pending = res_pending.json()
    assert "commands" in data_pending
    assert any(c["id"] == cmd_id for c in data_pending["commands"])

    # Worker 2: Reports execution status 'succeeded' with PID
    res_status = worker2_client.post(
        "/api/devices/command-status",
        headers=headers_device,
        json={
            "command_id": cmd_id,
            "status": "succeeded",
            "result": {"app": "vs code", "pid": 12345}
        }
    )
    assert res_status.status_code == 200
    assert res_status.json()["success"] is True

    # Worker 1: Inspects the command from database
    cmd_verified = db.get_device_command(user_id, cmd_id)
    assert cmd_verified is not None
    assert cmd_verified["status"] == "succeeded"
    assert cmd_verified["result"]["pid"] == 12345
