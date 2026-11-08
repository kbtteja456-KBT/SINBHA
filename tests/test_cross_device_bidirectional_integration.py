import pytest
import time
import json
from unittest.mock import MagicMock, AsyncMock, patch

from app import database as db
from app.models import Device
from app.device_relay import CommandRelayManager
from app.command_schema import validate_command_packet, is_command_supported_by_device
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def cross_device_user():
    email = f"cross_dev_{int(time.time() * 1000)}@sinbha.local"
    user = db.create_user(email, "Password123!", "Cross Device User", "UTC", is_verified=True)
    u_id = user["id"] if isinstance(user, dict) else user
    token = db.create_session(u_id)
    return {"id": u_id, "email": email, "token": token}


def test_phone_to_laptop_command_path(cross_device_user):
    """
    Phone -> Laptop: Phone initiates an action targeting Laptop (e.g. open_app or open_url).
    Validates packet structure, queues in DB, transitions through delivery and execution,
    and returns truthful execution receipt to the sender.
    """
    user_id = cross_device_user["id"]
    relay = CommandRelayManager()

    # 1. Register paired devices: Phone and Laptop
    phone_id = "phone_dev_1"
    laptop_id = "laptop_dev_1"
    with db.get_db_session() as session:
        session.add(Device(user_id=user_id, device_id=phone_id, name="Android Phone", platform="android", status="trusted", created_at=db.utc_now()))
        session.add(Device(user_id=user_id, device_id=laptop_id, name="Work Laptop", platform="windows", status="trusted", created_at=db.utc_now()))

    # 2. Construct phone -> laptop command packet
    cmd_id = f"cmd_p2l_{int(time.time() * 1000)}"
    cmd_packet = {
        "id": cmd_id,
        "type": "open_app",
        "sender_device": phone_id,
        "target_device": laptop_id,
        "payload": {"app": "chrome", "url": "https://classroom.google.com"},
        "expiry": 60,
    }
    is_valid, err, norm_packet = validate_command_packet(cmd_packet)
    assert is_valid is True, f"Validation failed: {err}"

    # 3. Initialize lifecycle in DB
    relay.init_command_lifecycle(
        cmd_id=cmd_id,
        user_id=user_id,
        sender_device=phone_id,
        target_device=laptop_id,
        cmd_type="open_app",
        status="queued"
    )

    stored = db.get_device_command(user_id, cmd_id)
    assert stored is not None
    assert stored["status"] == "queued"
    assert stored["target_device"] == laptop_id

    # 4. Laptop confirms execution with truthful receipt
    receipt = relay.update_command_status(
        user_id=user_id,
        cmd_id=cmd_id,
        status="succeeded",
        result={"launched": True, "app": "Google Chrome", "pid": 12345},
        client_timestamp="2026-11-08T18:00:00Z"
    )
    assert receipt["status"] == "succeeded"
    assert receipt["result"]["launched"] is True

    # 5. Verify persisted DB state
    persisted = db.get_device_command(user_id, cmd_id)
    assert persisted["status"] == "succeeded"
    assert persisted["result"]["launched"] is True


def test_laptop_to_phone_command_path(cross_device_user):
    """
    Laptop -> Phone: Laptop initiates a ring_phone command targeting Android phone.
    Ensures capability check passes for Android, lifecycle queues, executes, and returns receipt.
    """
    user_id = cross_device_user["id"]
    relay = CommandRelayManager()

    phone_id = "phone_dev_2"
    laptop_id = "laptop_dev_2"
    with db.get_db_session() as session:
        session.add(Device(user_id=user_id, device_id=phone_id, name="Android Phone", platform="android", status="trusted", created_at=db.utc_now()))
        session.add(Device(user_id=user_id, device_id=laptop_id, name="Windows Desktop", platform="windows", status="trusted", created_at=db.utc_now()))

    # Capability check for Android target
    assert is_command_supported_by_device("ring_phone", "android") is True

    cmd_id = f"cmd_l2p_{int(time.time() * 1000)}"
    relay.init_command_lifecycle(
        cmd_id=cmd_id,
        user_id=user_id,
        sender_device=laptop_id,
        target_device=phone_id,
        cmd_type="ring_phone",
        status="queued"
    )

    # Phone receives and acknowledges ring
    receipt = relay.update_command_status(
        user_id=user_id,
        cmd_id=cmd_id,
        status="succeeded",
        result={"sound_played": True, "volume": 100}
    )
    assert receipt["status"] == "succeeded"

    cmd_record = db.get_device_command(user_id, cmd_id)
    assert cmd_record["status"] == "succeeded"
    assert cmd_record["result"]["sound_played"] is True


def test_unsupported_capability_rejection():
    """
    Cross-device capability enforcement:
    If a target device does not declare or support a capability, command must be rejected.
    """
    # Windows client does not support 'ring_phone'
    assert is_command_supported_by_device("ring_phone", "windows") is False

    # Device with restricted permissions (e.g. only open_app and send_note)
    restricted_tools = ["open_app", "send_note"]
    assert is_command_supported_by_device("ring_phone", "android", restricted_tools) is False
    assert is_command_supported_by_device("take_screenshot", "android", restricted_tools) is False
    assert is_command_supported_by_device("open_app", "android", restricted_tools) is True


def test_emergency_stop_truthful_offline_explanation(cross_device_user):
    """
    Emergency STOP:
    When user triggers emergency stop, all pending commands on server are canceled.
    If any trusted device is offline, server truthfully informs user that the offline device
    cannot receive STOP until it reconnects.
    """
    user_id = cross_device_user["id"]
    client = TestClient(app)
    client.cookies.set("sinbha_session", cross_device_user["token"])

    phone_id = "phone_offline_1"
    laptop_id = "laptop_online_1"
    from datetime import timedelta
    with db.get_db_session() as session:
        session.add(Device(
            user_id=user_id,
            device_id=phone_id,
            name="Pixel 8",
            platform="android",
            status="trusted",
            created_at=db.utc_now() - timedelta(hours=5),
            last_seen_at=db.utc_now() - timedelta(hours=2),
            websocket_connected=False,
            last_ping_at=None
        ))
        session.add(Device(
            user_id=user_id,
            device_id=laptop_id,
            name="Dell XPS",
            platform="windows",
            status="trusted",
            created_at=db.utc_now(),
            last_seen_at=db.utc_now(),
            websocket_connected=True
        ))

    # Queue a pending command
    cmd_id = f"cmd_stop_test_{int(time.time() * 1000)}"
    db.create_device_command(
        user_id=user_id,
        cmd_id=cmd_id,
        sender_device=laptop_id,
        target_device=phone_id,
        cmd_type="open_app",
        payload={"name": "Maps"},
        expiry_seconds=60,
        status="queued"
    )

    # Mock laptop as online (connected websocket) and phone as offline
    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()

    from app.main import relay_manager
    relay_manager.active_websockets[(user_id, laptop_id)] = mock_ws
    if (user_id, phone_id) in relay_manager.active_websockets:
        del relay_manager.active_websockets[(user_id, phone_id)]

    try:
        response = client.post("/api/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"

        # Truthful offline message check
        assert "Pixel 8" in data["message"]
        assert "currently offline and cannot receive STOP until it reconnects" in data["message"]
        assert len(data.get("offline_devices", [])) >= 1

        # Verify command was canceled in DB
        cmd = db.get_device_command(user_id, cmd_id)
        assert cmd["status"] == "failed"
        assert "Emergency STOP" in cmd["error"]

        # Verify online laptop received stop control packet
        mock_ws.send_text.assert_called_once()
        sent_packet = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent_packet["type"] == "control"
        assert sent_packet["action"] == "stop"

    finally:
        relay_manager.active_websockets.pop((user_id, laptop_id), None)
