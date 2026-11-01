"""
Tests for Step 1C Item 7:
Relay rejection explanations and audit logging for all failure reasons:
unverified, not trusted, unsupported type, device offline, rate limited, blocked by stop.
"""
import pytest
import time
import json
import app.database as db
from app.device_relay import CommandRelayManager

@pytest.mark.asyncio
async def test_rejection_explanation_unverified(setup_test_db):
    """Unverified account is rejected with plain explanation and audit logged."""
    user = db.create_user("unver_relay_test@example.com", "Password123!", is_verified=False)
    user_id = user["id"]
    relay = CommandRelayManager()

    cmd = {
        "id": "cmd_unver_1",
        "sender_device": "sender_1",
        "target_device": "target_1",
        "type": "ring_phone",
        "payload": {}
    }
    res = await relay.relay_command(user_id, cmd)
    assert res["success"] is False
    assert res["error"] == "UNVERIFIED_ACCOUNT"
    assert "verification is required" in res["message"].lower()

    # Check audit log
    logs = db.get_audit_logs(user_id, limit=5)
    relay_logs = [l for l in logs if l["action"] == "DEVICE_COMMAND_RELAY"]
    assert len(relay_logs) >= 1
    details = json.loads(relay_logs[0]["details"])
    assert details["result"] == "unverified"


@pytest.mark.asyncio
async def test_rejection_explanation_not_trusted(setup_test_db):
    """Untrusted target device is rejected with plain explanation and audit logged."""
    user = db.create_user("untrusted_dev_test@example.com", "Password123!", is_verified=True)
    user_id = user["id"]
    relay = CommandRelayManager()

    # Register untrusted (pending) target device
    dev_target = db.create_or_register_device(user_id, "dev_target_untrusted", "Target Phone", "android")
    assert dev_target["status"] == "pending"

    # Register sender
    dev_sender = db.create_or_register_device(user_id, "dev_sender_1", "Sender Laptop", "windows", password="Password123!")

    cmd = {
        "id": "cmd_untrusted_1",
        "sender_device": "dev_sender_1",
        "target_device": "dev_target_untrusted",
        "type": "ring_phone",
        "payload": {}
    }
    res = await relay.relay_command(user_id, cmd)
    assert res["success"] is False
    assert res["error"] == "TARGET_UNTRUSTED"
    assert "pending pairing approval" in res["message"].lower() or "not trusted" in res["message"].lower()

    # Check audit log
    logs = db.get_audit_logs(user_id, limit=5)
    relay_logs = [l for l in logs if l["action"] == "DEVICE_COMMAND_RELAY"]
    assert len(relay_logs) >= 1
    details = json.loads(relay_logs[0]["details"])
    assert details["result"] == "target_untrusted"


@pytest.mark.asyncio
async def test_rejection_explanation_blocked_by_stop(setup_test_db):
    """Emergency stop blocks remote command and logs audit record."""
    user = db.create_user("stop_relay_test@example.com", "Password123!", is_verified=True)
    user_id = user["id"]
    relay = CommandRelayManager()

    db.set_emergency_stopped(user_id, True)

    cmd = {
        "id": "cmd_stop_1",
        "sender_device": "server",
        "target_device": "phone",
        "type": "ring_phone",
        "payload": {}
    }
    res = await relay.relay_command(user_id, cmd)
    assert res["success"] is False
    assert res["error"] == "BLOCKED_BY_STOP"
    assert "emergency stop is active" in res["message"].lower()

    # Check audit log
    logs = db.get_audit_logs(user_id, limit=5)
    relay_logs = [l for l in logs if l["action"] == "DEVICE_COMMAND_RELAY"]
    assert len(relay_logs) >= 1
    details = json.loads(relay_logs[0]["details"])
    assert details["result"] == "blocked_by_emergency_stop"


@pytest.mark.asyncio
async def test_rejection_explanation_rate_limited(setup_test_db):
    """Rate limited commands are rejected and audit logged."""
    user = db.create_user("rate_relay_test@example.com", "Password123!", is_verified=True)
    user_id = user["id"]
    relay = CommandRelayManager()

    dev1 = db.create_or_register_device(user_id, "dev_rt_sender", "Sender Laptop", "windows", password="Password123!")
    dev2 = db.create_or_register_device(user_id, "dev_rt_target", "Target Phone", "android")
    db.approve_device_pairing(user_id, dev2["pairing_code"])

    # Saturate rate limiter history (> 30 per min)
    now = time.time()
    relay.user_command_history[user_id] = [now] * 35

    cmd = {
        "id": f"cmd_rate_{int(now * 1000)}",
        "sender_device": "dev_rt_sender",
        "target_device": "dev_rt_target",
        "type": "sync_tasks",
        "payload": {}
    }
    res = await relay.relay_command(user_id, cmd)
    assert res["success"] is False
    assert res["error"] == "RATE_LIMITED"
    assert "rate limit exceeded" in res["message"].lower()

    # Check audit log
    logs = db.get_audit_logs(user_id, limit=5)
    relay_logs = [l for l in logs if l["action"] == "DEVICE_COMMAND_RELAY"]
    assert len(relay_logs) >= 1
    details = json.loads(relay_logs[0]["details"])
    assert details["result"] == "rate_limited"


@pytest.mark.asyncio
async def test_rejection_explanation_unsupported_type(setup_test_db):
    """Commands unsupported by target device are rejected and audit logged."""
    user = db.create_user("unsupp_relay_test@example.com", "Password123!", is_verified=True)
    user_id = user["id"]
    relay = CommandRelayManager()

    dev1 = db.create_or_register_device(user_id, "dev_unsup_sender", "Sender Laptop", "windows", password="Password123!")
    dev2 = db.create_or_register_device(user_id, "dev_unsup_target", "Target Phone", "android")
    db.approve_device_pairing(user_id, dev2["pairing_code"])

    # Phone reports supporting only 'ring_phone', NOT 'lock_workstation'
    relay.record_device_capabilities(user_id, "dev_unsup_target", "android", "1.4.5", supported_tools=["ring_phone"])

    cmd = {
        "id": "cmd_unsup_1",
        "sender_device": "dev_unsup_sender",
        "target_device": "dev_unsup_target",
        "type": "open_url",
        "payload": {"url": "https://example.com"}
    }
    res = await relay.relay_command(user_id, cmd)
    assert res["success"] is False
    assert res["error"] == "UNSUPPORTED_TYPE"
    assert "does not support command type" in res["message"].lower()

    # Check audit log
    logs = db.get_audit_logs(user_id, limit=5)
    relay_logs = [l for l in logs if l["action"] == "DEVICE_COMMAND_RELAY"]
    assert len(relay_logs) >= 1
    details = json.loads(relay_logs[0]["details"])
    assert details["result"] == "unsupported_command_type"


@pytest.mark.asyncio
async def test_rejection_explanation_device_offline(setup_test_db):
    """Offline device is queued persistently in database, logged in audit, and explained plainly."""
    from app.agent_tools import handle_open_app

    user = db.create_user("offline_relay_test@example.com", "Password123!", is_verified=True)
    user_id = user["id"]
    relay = CommandRelayManager()

    dev1 = db.create_or_register_device(user_id, "dev_off_sender", "Sender Laptop", "windows", password="Password123!")
    dev2 = db.create_or_register_device(user_id, "dev_off_target", "Offline Phone", "android")
    db.approve_device_pairing(user_id, dev2["pairing_code"])

    # Set last_seen_at and last_ping_at to the past so it is truly offline
    from datetime import datetime, timezone, timedelta
    old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
    with db.get_db_session() as session:
        from app.database import Device
        d_row = session.query(Device).filter(Device.device_id == "dev_off_target").first()
        if d_row:
            d_row.last_seen_at = old_time
            d_row.last_ping_at = old_time
            d_row.websocket_connected = False

    res = await handle_open_app(
        user_id=user_id,
        args={"name": "whatsapp", "target_device": "Offline Phone"},
        ctx={"user_email": "offline_relay_test@example.com", "db": db, "relay_manager": relay}
    )

    assert res["status"] == "queued"
    assert "currently offline" in res["message"].lower()

    # Verify audit log records queued_db
    logs = db.get_audit_logs(user_id, limit=5)
    relay_logs = [l for l in logs if l["action"] == "DEVICE_COMMAND_RELAY"]
    assert len(relay_logs) >= 1
    details = json.loads(relay_logs[0]["details"])
    assert details["result"] == "queued_db"

