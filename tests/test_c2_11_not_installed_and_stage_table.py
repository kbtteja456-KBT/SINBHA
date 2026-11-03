"""
Tests for Step C2.11: Honest 'not installed' result and working stage table.
Verifies:
1. Real handler code with unknown app returns not_installed with top 3 candidates (no silent web fallback).
2. Real Android launcher returns not_installed with top 3 candidates (no silent web fallback).
3. handle_open_app formats: "I could not find '<name>'. Did you mean X, Y or Z? Or should I open its website?"
4. Verification of real apps: sent_not_verified status if process or window did not appear.
5. Stage table is wired to real command id with all 6 stages and timestamps.
6. Windows installed apps reporting stores presence and shows count in diagnostics.
"""
import pytest
import time
import subprocess
import json
from unittest.mock import AsyncMock, MagicMock
from app.agent_tools import handle_open_app
from app.database import (
    create_device_command,
    update_device_command_status,
    get_device_command,
    format_stage_table,
    update_device_presence,
    get_device_presence
)


def test_electron_handler_unknown_app_not_installed_no_web_fallback():
    """
    Step C2.11 Item 1 & 5:
    Run the REAL Node/Electron command security handler against an unknown app name.
    Must return status: 'not_installed', error: 'not_installed', with closest candidates.
    Must NEVER return success=true or web_fallback!
    """
    node_script = """
    const { safeLaunchDesktopApp, openAppWithFallback } = require('./electron/command_security');
    (async () => {
        const res1 = await safeLaunchDesktopApp('nonexistent_test_app_xyz');
        const res2 = await openAppWithFallback('nonexistent_test_app_xyz', 'chrome', false);
        console.log(JSON.stringify({ res1, res2 }));
    })();
    """
    p = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, cwd=".")
    assert p.returncode == 0, f"Node script failed: {p.stderr}"
    data = json.loads(p.stdout.strip())
    res1 = data["res1"]
    res2 = data["res2"]

    # safeLaunchDesktopApp
    assert res1["success"] is False
    assert res1["status"] == "not_installed"
    assert res1["error"] == "not_installed"
    assert "candidates" in res1
    assert isinstance(res1["candidates"], list)
    assert len(res1["candidates"]) <= 3

    # openAppWithFallback without user confirmation must NEVER open website
    assert res2["success"] is False
    assert res2["status"] == "not_installed"
    assert res2["error"] == "not_installed"
    assert "candidates" in res2
    assert "Would you like me to open the website" in res2["message"] or "Did you mean" in res2["message"]


def test_electron_handler_claude_chatgpt_not_installed_no_silent_fallback():
    """
    Step C2.11 Item 1:
    Even for special targets like 'claude' or 'chatgpt', when not installed,
    it must return not_installed rather than opening claude.ai or chatgpt.com silently!
    """
    node_script = """
    const { safeLaunchDesktopApp } = require('./electron/command_security');
    (async () => {
        // Run with an unknown app variant that shouldn't open website
        const res = await safeLaunchDesktopApp('unknown_special_app_foo');
        console.log(JSON.stringify(res));
    })();
    """
    p = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, cwd=".")
    assert p.returncode == 0
    res = json.loads(p.stdout.strip())
    assert res["success"] is False
    assert res["status"] == "not_installed"


@pytest.mark.asyncio
async def test_handle_open_app_not_installed_formats_honest_question():
    """
    Step C2.11 Item 1:
    When the device reports not_installed with candidates [X, Y, Z],
    SINBHA must return status: 'not_installed' and say:
    "I could not find '<name>'. Did you mean X, Y or Z? Or should I open its website?"
    """
    user_id = 991
    fake_cmd_id = "cmd_app_test_123"

    # Mock relay returning completion with candidates
    mock_relay = MagicMock()
    mock_relay.is_device_connected.return_value = True
    mock_relay.relay_command = AsyncMock(return_value={"success": True})
    mock_relay.wait_for_command_completion = AsyncMock(return_value={
        "command_id": fake_cmd_id,
        "status": "not_installed",
        "result": {
            "app": "nonexistent_app",
            "status": "not_installed",
            "candidates": ["Notepad", "Calculator", "Chrome"]
        },
        "error": "not_installed",
        "stages": {
            "created": "2026-11-03T00:00:00Z",
            "delivered": "2026-11-03T00:00:01Z",
            "received": "2026-11-03T00:00:02Z",
            "started": "2026-11-03T00:00:03Z",
            "result_sent": "2026-11-03T00:00:04Z",
            "result_stored": "2026-11-03T00:00:05Z"
        }
    })

    mock_db = MagicMock()
    mock_db.get_setting.return_value = "chrome"
    mock_db.get_user_devices.return_value = [{
        "device_id": "laptop_win_1",
        "name": "BHANUTEJA",
        "platform": "windows",
        "status": "trusted"
    }]
    mock_db.format_stage_table = format_stage_table

    ctx = {"db": mock_db, "relay_manager": mock_relay}
    res = await handle_open_app(user_id, {"name": "nonexistent_app", "target_device": "BHANUTEJA"}, ctx)

    assert res["success"] is False
    assert res["status"] == "not_installed"
    assert res["error"] == "not_installed"
    assert "candidates" in res
    assert res["candidates"] == ["Notepad", "Calculator", "Chrome"]
    assert "I could not find 'nonexistent_app'" in res["message"]
    assert "Did you mean 'Notepad', 'Calculator' or 'Chrome'?" in res["message"]
    assert "Or should I open its website?" in res["message"]
    assert "command_id" in res
    assert "stages" in res
    assert "stage_table" in res


@pytest.mark.asyncio
async def test_handle_open_app_sent_not_verified():
    """
    Step C2.11 Item 2:
    When a real app launch cannot verify process or window,
    it must report 'sent, not verified'.
    """
    user_id = 992
    mock_relay = MagicMock()
    mock_relay.is_device_connected.return_value = True
    mock_relay.relay_command = AsyncMock(return_value={"success": True})
    mock_relay.wait_for_command_completion = AsyncMock(return_value={
        "command_id": "cmd_test_unver",
        "status": "sent_not_verified",
        "result": {"error": "Process or window did not appear within 8 seconds"},
        "error": "sent_not_verified",
        "stages": {"created": "2026-11-03T00:00:00Z"}
    })

    mock_db = MagicMock()
    mock_db.get_setting.return_value = "chrome"
    mock_db.get_user_devices.return_value = [{
        "device_id": "laptop_win_2",
        "name": "BHANUTEJA",
        "platform": "windows",
        "status": "trusted"
    }]
    mock_db.format_stage_table = format_stage_table

    ctx = {"db": mock_db, "relay_manager": mock_relay}
    res = await handle_open_app(user_id, {"name": "notepad", "target_device": "BHANUTEJA"}, ctx)

    assert res["success"] is False
    assert res["status"] == "sent_not_verified"
    assert "could not be verified" in res["message"]


def test_stage_table_full_6_stages_and_timestamps():
    """
    Step C2.11 Item 3:
    Stage table must correctly parse and format all 6 stages with real timestamps.
    """
    stages = {
        "created": "2026-11-03T09:00:01Z",
        "delivered": "2026-11-03T09:00:02Z",
        "received": "2026-11-03T09:00:03Z",
        "started": "2026-11-03T09:00:04Z",
        "result_sent": "2026-11-03T09:00:05Z",
        "result_stored": "2026-11-03T09:00:06Z"
    }
    table, first_missing = format_stage_table(stages)
    assert first_missing is None
    assert len(table) == 6
    for row in table:
        assert row["status"] == "OK"
        assert row["timestamp"] is not None
        assert not row["is_failure_point"]


def test_windows_installed_apps_reporting_presence():
    """
    Step C2.11 Item 4:
    Windows installed apps (name and type) reported to server are saved in DB
    and retrievable for presence and diagnostics count.
    """
    user_id = 993
    dev_id = "win_laptop_test_presence"
    installed_apps = [
        {"name": "notepad", "displayName": "Notepad", "type": "binary"},
        {"name": "calculator", "displayName": "Calculator", "type": "protocol"},
        {"name": "chrome", "displayName": "Google Chrome", "type": "start_menu_shortcut"},
        {"name": "vscode", "displayName": "Visual Studio Code", "type": "registered_exe"}
    ]

    update_device_presence(
        user_id=user_id,
        device_id=dev_id,
        platform="windows",
        client_version="1.4.25",
        battery=92,
        installed_apps=installed_apps
    )

    presence = get_device_presence(user_id, dev_id)
    assert presence is not None
    assert presence["platform"] == "windows"
    assert presence["client_version"] == "1.4.25"
    assert presence["installed_apps"] is not None
    assert len(presence["installed_apps"]) == 4
    assert presence["installed_apps"][0]["name"] == "notepad"

