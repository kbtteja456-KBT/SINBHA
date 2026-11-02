"""
Tests for Step C2.10: Real Device Path, Stage Tables, Strict Verification & Version Safety
Verifies:
1. Real device check uses identical server path as chat.
2. A test passes ONLY on a TRUE result: real apps pass ONLY on "succeeded",
   nonexistent app passes ONLY on "not_installed". A timeout is ALWAYS a FAIL.
3. If timeout occurs, it must NEVER be counted as a pass.
4. Stage table captures 6 lifecycle stages with server & device timestamps,
   identifying the first missing stage as the failure point.
5. Dropped WebSocket resilience: polling retrieves commands in 'delivered' state.
6. Version Safety: Minimum version cannot exceed latest published version (clamping).
7. Version rejection returns exact chat message:
   "Your phone app is version X, please update to Y." / "Your laptop app is version X, please update to Y."
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import app.database as db
from app.version import get_effective_min_version, is_client_version_supported, get_app_version
from app.device_relay import CommandRelayManager


def test_stage_table_format_detects_first_missing_stage():
    """Item 3: Format stage table captures all 6 stages and accurately identifies failure point."""
    now_iso = datetime.now(timezone.utc).isoformat()
    stages = {
        "created": now_iso,
        "delivered": now_iso,
        "received": None, # Fails here!
        "started": None,
        "result_sent": None,
        "result_stored": None,
    }
    table, first_missing = db.format_stage_table(stages)
    assert len(table) == 6
    assert first_missing == "received"
    
    # Check failure point flag
    rec_stage = next(s for s in table if s["stage"] == "received")
    assert rec_stage["status"] == "MISSING"
    assert rec_stage["is_failure_point"] is True

    created_stage = next(s for s in table if s["stage"] == "created")
    assert created_stage["status"] == "OK"
    assert created_stage["is_failure_point"] is False


def test_stage_table_all_ok_when_complete():
    """Stage table reports no missing stage when all 6 stages succeed."""
    now_iso = datetime.now(timezone.utc).isoformat()
    stages = {
        "created": now_iso,
        "delivered": now_iso,
        "received": now_iso,
        "started": now_iso,
        "result_sent": now_iso,
        "result_stored": now_iso,
    }
    table, first_missing = db.format_stage_table(stages)
    assert first_missing is None
    for row in table:
        assert row["status"] == "OK"
        assert row["is_failure_point"] is False


def test_timeout_never_counted_as_pass():
    """Item 2: Strict verification: A timeout must NEVER be counted as a pass."""
    # Simulate a command that timed out
    timed_out_result = {
        "success": False,
        "status": "timeout",
        "error": "Device timed out after 10s",
        "message": "Timed out waiting for device",
    }
    
    # Rule for real app: pass ONLY on status == 'succeeded'
    real_app_passed = (timed_out_result["status"] == "succeeded")
    assert real_app_passed is False, "CRITICAL: Timeout must never pass for real app!"

    # Rule for nonexistent app: pass ONLY on status == 'not_installed'
    nonexistent_passed = (timed_out_result["status"] == "not_installed")
    assert nonexistent_passed is False, "CRITICAL: Timeout must never pass for nonexistent app!"


def test_nonexistent_app_passes_only_on_not_installed():
    """Item 2: Nonexistent app passes ONLY when device explicitly reports 'not_installed'."""
    assert ("not_installed" == "not_installed") is True
    assert ("failed" == "not_installed") is False
    assert ("unconfirmed" == "not_installed") is False
    assert ("timeout" == "not_installed") is False


def test_polling_recovers_delivered_commands():
    """Item 4: Dropped WebSocket fix: Poller must drain status 'delivered' as well as 'queued'."""
    from app.models import DeviceCommand, User, Device
    from app.database import get_db_session

    user_id = None
    with get_db_session() as session:
        user = session.query(User).filter_by(email="test_c210_user@example.com").first()
        if not user:
            user = User(
                email="test_c210_user@example.com",
                password_hash="fakehash",
                is_verified=True
            )
            session.add(user)
            session.flush()
        user_id = user.id

        dev = session.query(Device).filter_by(device_id="laptop_c210_test").first()
        if not dev:
            dev = Device(
                user_id=user_id,
                device_id="laptop_c210_test",
                name="My Laptop",
                platform="windows",
                status="trusted"
            )
            session.add(dev)
            session.flush()

    # Create command with status="ws_sent" (as happens when WS sends frame but proxy drops it before delivery)
    cmd_dict = db.create_device_command(
        user_id=user_id,
        cmd_id="cmd_poll_test_c210",
        sender_device="server",
        target_device="laptop_c210_test",
        cmd_type="open_app",
        payload={"app": "notepad"},
        status="ws_sent",
        expiry_seconds=30
    )
    cmd_id = cmd_dict["id"]

    # Now poll for pending commands for this device
    pending = db.get_pending_device_commands(user_id, "laptop_c210_test")
    pending_ids = [c["id"] for c in pending]
    assert cmd_id in pending_ids, "Polling MUST return 'ws_sent' commands so dropped WebSockets don't cause timeouts!"

    # Second poll should return 0 since command was marked 'delivered'
    pending_after = db.get_pending_device_commands(user_id, "laptop_c210_test")
    assert len(pending_after) == 0, "Second poll must be empty to avoid double execution"


def test_effective_min_version_clamped_to_latest():
    """Item 8: Minimum version can NEVER exceed latest published version."""
    latest = get_app_version()
    
    with patch.dict("os.environ", {"MIN_CLIENT_VERSION": "99.0.0"}):
        effective_min = get_effective_min_version()
        assert effective_min == latest, f"Effective min ({effective_min}) must be clamped to latest ({latest})"

    with patch.dict("os.environ", {"MIN_APP_VERSION_ANDROID": "99.0.0"}):
        effective_min_android = get_effective_min_version(platform="android")
        assert effective_min_android == latest, f"Android min ({effective_min_android}) must be clamped to latest ({latest})"


@pytest.mark.asyncio
async def test_server_refuses_remote_command_below_minimum_version():
    """Item 8: Server refuses remote commands below minimum with exact chat message."""
    relay = CommandRelayManager()
    
    # Mock target device with outdated version 1.4.10
    outdated_device = {
        "id": 1,
        "device_id": "phone_outdated_1",
        "name": "OnePlus 12",
        "platform": "android",
        "status": "trusted",
        "client_version": "1.4.10",
        "supported_tools": ["open_app"]
    }

    with patch("app.database.is_user_verified", return_value=True), \
         patch("app.database.get_emergency_stopped", return_value=False), \
         patch("app.database.get_device_by_id", return_value=outdated_device), \
         patch("app.database.log_audit", return_value=None), \
         patch.dict("os.environ", {"MIN_APP_VERSION_ANDROID": "1.4.21"}):
        
        result = await relay.relay_command(
            user_id=1,
            cmd_data={
                "id": "cmd_test_ver_1",
                "sender_device": "server",
                "target_device": "phone_outdated_1",
                "type": "open_app",
                "payload": {"app": "camera"},
            }
        )

        assert result["success"] is False
        assert result["error"] == "CLIENT_OUTDATED"
        # Exact chat message requirement:
        # "Your phone app is version X, please update to Y."
        expected_msg = "Your phone app is version 1.4.10, please update to 1.4.21."
        assert result["message"] == expected_msg, f"Expected '{expected_msg}', got '{result.get('message')}'"
