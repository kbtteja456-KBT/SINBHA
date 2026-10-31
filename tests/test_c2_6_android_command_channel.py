"""
Unit & Integration Tests for Step C2.6:
Android Companion Command Channel Reliability, Scoped Command Tokens,
Lifecycle Waiters, Typo-Tolerant Installed Apps Matching, and Self-Test.
"""

import os
import sys
import time
import json
import asyncio
import pytest
from fastapi.testclient import TestClient

# Ensure root directory is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.main import app
from app import database as db
from app.main import relay_manager
from app.models import DeviceToken, Device

@pytest.fixture(autouse=True)
def setup_test_db():
    db.init_db()
    # Reset relay caches
    relay_manager.active_websockets.clear()
    relay_manager.seen_command_ids.clear()
    relay_manager.command_lifecycles.clear()
    relay_manager._lifecycle_waiters.clear()
    relay_manager.device_capabilities.clear()
    relay_manager.device_installed_apps.clear()
    relay_manager.device_telemetry.clear()
    yield

def create_test_user(email="c26_user@example.com"):
    # Delete if exists
    with db.get_db_session() as session:
        from sqlalchemy import select, delete
        from app.models import User
        u = session.scalar(select(User).where(User.email == email))
        if u:
            session.execute(delete(User).where(User.id == u.id))
    user = db.create_user(email, "Password123!", is_18=True, agreed_terms=True)
    return user

def register_and_trust_device(user_id: int, device_id: str, platform="android", name="Test Android"):
    dev = db.create_or_register_device(user_id, device_id, name=name, platform=platform)
    with db.get_db_session() as session:
        from sqlalchemy import select
        d = session.scalar(select(Device).where(Device.user_id == user_id, Device.device_id == device_id))
        if d:
            d.status = "trusted"
    return db.get_device_by_id(user_id, device_id)


# ========================================================
# 1. Scoped Device Command Token Tests
# ========================================================

def test_device_command_token_creation_and_scoping():
    """
    Step C2.6 Item 1:
    Dedicated device command token (snb_cmd_...) scoped ONLY to command endpoints.
    Must NOT work for chat, export, or reminder actions.
    """
    client = TestClient(app)
    user = create_test_user("cmd_token_scope@example.com")
    device_id = "phone_cmd_test_1"
    register_and_trust_device(user["id"], device_id)

    # 1. Create command token
    cmd_info = db.create_device_command_token(user["id"], device_id=device_id, device_name="OnePlus 12")
    cmd_token = cmd_info["command_token"]
    assert cmd_token.startswith("snb_cmd_")
    assert cmd_info["scope"] == "command_only"

    # 2. Command endpoints must SUCCEED with command token
    headers = {"Authorization": f"Bearer {cmd_token}"}

    # Pending commands
    res_pending = client.get(f"/api/devices/commands/pending?device_id={device_id}", headers=headers)
    assert res_pending.status_code == 200
    assert "commands" in res_pending.json()

    # Heartbeat
    res_hb = client.post("/api/devices/heartbeat", json={"device_id": device_id, "battery": 88}, headers=headers)
    assert res_hb.status_code == 200
    assert res_hb.json()["status"] == "ok"

    # Command status update
    res_st = client.post("/api/devices/command-status", json={
        "command_id": "dummy_cmd_1",
        "status": "received"
    }, headers=headers)
    assert res_st.status_code == 200

    # 3. Account endpoints must FAIL (403 Forbidden) with command token
    res_chat = client.post("/api/chat", json={"message": "Hello AI"}, headers=headers)
    assert res_chat.status_code == 403
    assert "Device command token scope is restricted strictly" in res_chat.json()["detail"]

    res_export = client.get("/api/account/export", headers=headers)
    assert res_export.status_code == 403
    assert "Device command token scope is restricted strictly" in res_export.json()["detail"]

    # Reminder endpoints must FAIL (403 Forbidden) with command token
    res_reminders = client.get("/api/reminders/upcoming", headers=headers)
    assert res_reminders.status_code == 403


def test_command_token_revocation_per_device_logout():
    """
    Step C2.6 Item 1:
    Logging out a device revokes ONLY its command token, not other devices.
    """
    client = TestClient(app)
    user = create_test_user("cmd_rev_logout@example.com")
    dev_a = "phone_a"
    dev_b = "phone_b"
    register_and_trust_device(user["id"], dev_a)
    register_and_trust_device(user["id"], dev_b)

    token_a = db.create_device_command_token(user["id"], device_id=dev_a)["command_token"]
    token_b = db.create_device_command_token(user["id"], device_id=dev_b)["command_token"]

    # Verify both work
    assert client.get(f"/api/devices/commands/pending?device_id={dev_a}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 200
    assert client.get(f"/api/devices/commands/pending?device_id={dev_b}", headers={"Authorization": f"Bearer {token_b}"}).status_code == 200

    # Logout phone A
    res_logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token_a}"})
    assert res_logout.status_code == 200

    # Phone A is now rejected (401)
    res_a_after = client.get(f"/api/devices/commands/pending?device_id={dev_a}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a_after.status_code == 401

    # Phone B is still valid!
    res_b_after = client.get(f"/api/devices/commands/pending?device_id={dev_b}", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b_after.status_code == 200


def test_command_token_revocation_on_disconnect_all():
    """
    Step C2.6 Item 1:
    Disconnect All immediately revokes all command tokens for the user.
    """
    client = TestClient(app)
    user = create_test_user("cmd_rev_discall@example.com")
    session_token = db.create_session(user["id"])
    sess_headers = {"Cookie": f"sinbha_session={session_token}"}

    dev_1 = "phone_disc_1"
    register_and_trust_device(user["id"], dev_1)
    token_1 = db.create_device_command_token(user["id"], device_id=dev_1)["command_token"]

    assert client.get(f"/api/devices/commands/pending?device_id={dev_1}", headers={"Authorization": f"Bearer {token_1}"}).status_code == 200

    # Disconnect all
    res_disc = client.post("/api/devices/disconnect-all", headers=sess_headers)
    assert res_disc.status_code == 200

    # Token 1 must now be revoked
    assert client.get(f"/api/devices/commands/pending?device_id={dev_1}", headers={"Authorization": f"Bearer {token_1}"}).status_code == 401


def test_command_token_revocation_on_password_change():
    """
    Step C2.6 Item 1:
    Password change invalidates all command tokens and sessions across all devices.
    """
    client = TestClient(app)
    user = create_test_user("cmd_rev_pwd@example.com")
    session_token = db.create_session(user["id"])
    sess_headers = {"Cookie": f"sinbha_session={session_token}"}

    dev_1 = "phone_pwd_1"
    register_and_trust_device(user["id"], dev_1)
    token_1 = db.create_device_command_token(user["id"], device_id=dev_1)["command_token"]

    assert client.get(f"/api/devices/commands/pending?device_id={dev_1}", headers={"Authorization": f"Bearer {token_1}"}).status_code == 200

    # Change password
    res_chg = client.post("/api/account/change-password", json={
        "old_password": "Password123!",
        "new_password": "BrandNewPassword456!"
    }, headers=sess_headers)
    assert res_chg.status_code == 200

    # Token 1 is now invalid
    assert client.get(f"/api/devices/commands/pending?device_id={dev_1}", headers={"Authorization": f"Bearer {token_1}"}).status_code == 401


# ========================================================
# 2. Unified Lifecycle Waiter Tests (HTTP report, /ack, WS)
# ========================================================

@pytest.mark.asyncio
async def test_unified_lifecycle_waiter_resolved_by_http_report():
    """
    Step C2.6 Item 2:
    The waiter waiting for command confirmation must be resolved when
    the native companion reports status to /api/devices/command-status.
    """
    user = create_test_user("waiter_http@example.com")
    cmd_id = "test_cmd_lifecycle_http"
    relay_manager.init_command_lifecycle(cmd_id, user["id"], "laptop", "phone", "open_app")

    client = TestClient(app)
    token = db.create_device_command_token(user["id"], "phone")["command_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Start async wait in background
    async def run_waiter():
        return await relay_manager.wait_for_command_completion(user["id"], cmd_id, timeout=5.0)

    waiter_task = asyncio.create_task(run_waiter())
    await asyncio.sleep(0.05)

    # Companion reports "received" -> waiter should continue waiting
    client.post("/api/devices/command-status", json={"command_id": cmd_id, "status": "received"}, headers=headers)
    assert not waiter_task.done()

    # Companion reports "started" -> waiter should continue waiting
    client.post("/api/devices/command-status", json={"command_id": cmd_id, "status": "started"}, headers=headers)
    assert not waiter_task.done()

    # Companion reports "succeeded" with real result -> waiter completes immediately!
    client.post("/api/devices/command-status", json={
        "command_id": cmd_id,
        "status": "succeeded",
        "result": {"package": "com.anthropic.claude", "method": "overlay_exemption"}
    }, headers=headers)

    res = await asyncio.wait_for(waiter_task, timeout=1.0)
    assert res["status"] == "succeeded"
    assert res["result"]["package"] == "com.anthropic.claude"


@pytest.mark.asyncio
async def test_unified_lifecycle_waiter_resolved_by_ack_endpoint():
    """
    Step C2.6 Item 2:
    The /ack endpoint must resolve the SAME lifecycle waiter.
    """
    user = create_test_user("waiter_ack@example.com")
    cmd_id = "test_cmd_lifecycle_ack"
    relay_manager.init_command_lifecycle(cmd_id, user["id"], "laptop", "phone", "open_app")

    client = TestClient(app)
    token = db.create_device_command_token(user["id"], "phone")["command_token"]
    headers = {"Authorization": f"Bearer {token}"}

    async def run_waiter():
        return await relay_manager.wait_for_command_completion(user["id"], cmd_id, timeout=5.0)

    waiter_task = asyncio.create_task(run_waiter())
    await asyncio.sleep(0.05)

    # /ack called with executed
    res_ack = client.post(f"/api/devices/commands/{cmd_id}/ack", json={
        "status": "executed",
        "result": {"package": "com.snapchat.android"}
    }, headers=headers)
    assert res_ack.status_code == 200

    res = await asyncio.wait_for(waiter_task, timeout=1.0)
    assert res["status"] == "succeeded"
    assert res["result"]["package"] == "com.snapchat.android"


@pytest.mark.asyncio
async def test_unified_lifecycle_waiter_handles_needs_tap():
    """
    Step C2.6 Item 5:
    When Android restricts background start, reporting 'needs_tap' completes
    the waiter honestly and provides honest feedback.
    """
    user = create_test_user("waiter_tap@example.com")
    cmd_id = "test_cmd_tap"
    relay_manager.init_command_lifecycle(cmd_id, user["id"], "laptop", "phone", "open_app")

    client = TestClient(app)
    token = db.create_device_command_token(user["id"], "phone")["command_token"]
    headers = {"Authorization": f"Bearer {token}"}

    async def run_waiter():
        return await relay_manager.wait_for_command_completion(user["id"], cmd_id, timeout=5.0)

    waiter_task = asyncio.create_task(run_waiter())
    await asyncio.sleep(0.05)

    client.post("/api/devices/command-status", json={
        "command_id": cmd_id,
        "status": "needs_tap",
        "result": {"package": "com.anthropic.claude", "needs_tap": True},
        "error": "needs a tap"
    }, headers=headers)

    res = await asyncio.wait_for(waiter_task, timeout=1.0)
    assert res["status"] == "needs_tap"
    assert res["result"]["needs_tap"] is True


# ========================================================
# 3. Installed Apps Handshake & Typo-Tolerant Matching
# ========================================================

def test_capability_handshake_and_typo_tolerant_matching():
    """
    Step C2.6 Item 6:
    Phone reports installed apps (name and package).
    Typo-tolerant matching resolves misspellings without falling back silently to website.
    """
    user = create_test_user("handshake_apps@example.com")
    device_id = "phone_typo_test"
    register_and_trust_device(user["id"], device_id)

    installed_apps = [
        {"name": "Snapchat", "package": "com.snapchat.android"},
        {"name": "Files", "package": "com.google.android.documentsui"},
        {"name": "Claude", "package": "com.anthropic.claude"},
        {"name": "Settings", "package": "com.android.settings"},
        {"name": "YouTube", "package": "com.google.android.youtube"}
    ]

    # Handshake via record_device_capabilities
    relay_manager.record_device_capabilities(
        user["id"],
        device_id,
        platform="android",
        app_version="1.4.7",
        installed_apps=installed_apps
    )

    # 1. Exact match
    match1 = relay_manager.find_installed_app_match(user["id"], device_id, "Snapchat")
    assert match1 is not None
    assert match1["package"] == "com.snapchat.android"

    # 2. Typo: "snap chat"
    match2 = relay_manager.find_installed_app_match(user["id"], device_id, "snap chat")
    assert match2 is not None
    assert match2["package"] == "com.snapchat.android"

    # 3. Typo: "claud" -> Claude
    match3 = relay_manager.find_installed_app_match(user["id"], device_id, "claud")
    assert match3 is not None
    assert match3["package"] == "com.anthropic.claude"

    # 4. Files
    match4 = relay_manager.find_installed_app_match(user["id"], device_id, "files")
    assert match4 is not None
    assert match4["package"] == "com.google.android.documentsui"

    # 5. Nonexistent app -> None (NEVER falls back silently to a website)
    match_fake = relay_manager.find_installed_app_match(user["id"], device_id, "NonExistentApp123")
    assert match_fake is None


# ========================================================
# 4. Fake Phone Interactive Flow Test
# ========================================================

@pytest.mark.asyncio
async def test_fake_phone_command_channel_full_flow():
    """
    Simulates a fake phone companion executing a full real-time command sequence:
    1. Authenticate with command token
    2. Handshake with installed apps
    3. Receive open_app for 'Snapchat'
    4. Report lifecycle (received -> started -> succeeded)
    5. Receive open_app for nonexistent app
    6. Report lifecycle (received -> started -> failed: 'not installed')
    """
    client = TestClient(app)
    user = create_test_user("fake_phone_sim@example.com")
    device_id = "fake_android_phone"
    register_and_trust_device(user["id"], device_id)

    token = db.create_device_command_token(user["id"], device_id=device_id)["command_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Heartbeat with installed apps
    res_hb = client.post("/api/devices/heartbeat", json={
        "device_id": device_id,
        "platform": "android",
        "battery": 92,
        "is_charging": True,
        "installed_apps": [
            {"name": "Snapchat", "package": "com.snapchat.android"},
            {"name": "Files", "package": "com.google.android.documentsui"},
            {"name": "Claude", "package": "com.anthropic.claude"},
            {"name": "Settings", "package": "com.android.settings"}
        ]
    }, headers=headers)
    assert res_hb.status_code == 200

    # 2. Server sends command to phone
    cmd_id = f"cmd_snap_{int(time.time()*1000)}"
    relay_manager.init_command_lifecycle(cmd_id, user["id"], "laptop", device_id, "open_app")

    # Companion reports lifecycle
    client.post("/api/devices/command-status", json={"command_id": cmd_id, "status": "received"}, headers=headers)
    client.post("/api/devices/command-status", json={"command_id": cmd_id, "status": "started"}, headers=headers)
    client.post("/api/devices/command-status", json={
        "command_id": cmd_id,
        "status": "succeeded",
        "result": {"app": "snapchat", "package": "com.snapchat.android", "method": "overlay_exemption"}
    }, headers=headers)

    entry = relay_manager.get_command_lifecycle(cmd_id)
    assert entry["status"] == "succeeded"
    assert entry["result"]["package"] == "com.snapchat.android"

    # 3. Nonexistent app command
    cmd_fake_id = f"cmd_fake_{int(time.time()*1000)}"
    relay_manager.init_command_lifecycle(cmd_fake_id, user["id"], "laptop", device_id, "open_app")

    client.post("/api/devices/command-status", json={"command_id": cmd_fake_id, "status": "received"}, headers=headers)
    client.post("/api/devices/command-status", json={
        "command_id": cmd_fake_id,
        "status": "failed",
        "error": "App 'NonExistentApp' is not installed on this Android device."
    }, headers=headers)

    entry_fake = relay_manager.get_command_lifecycle(cmd_fake_id)
    assert entry_fake["status"] == "failed"
    assert "not installed" in entry_fake["error"]
