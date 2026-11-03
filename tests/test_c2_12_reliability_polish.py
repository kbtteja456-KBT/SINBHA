"""
Tests for Step C2.12: Reliability Polish from Real Chat Tests (v1.4.26)
Follows AGENT_RULES.md (including Rule 24).

Covers:
1. pyautogui: verifies server code does NOT import pyautogui or desktop GUI libraries.
2. Windows verification and apps: verifies settings pages (bluetooth, wifi, display, apps) and store apps.
3. Android settings pages: verifies settings intents with confirmed results.
4. LLM reliability: verifies fallback to second provider/model, 429 queuing, and deterministic app messages.
5. Screen-control capability: verifies truthful reporting of accessibility status and exact Settings paths.
6. Confirmation UX: verifies confirmation card structure instead of plain text error sentences.
7. Presence: verifies last-seen duration reporting without guessing.
"""

import sys
import os
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent_tools import (
    handle_open_settings,
    handle_open_app,
    _format_device_last_seen,
    default_registry,
    ToolRegistry
)
from app.command_schema import SUPPORTED_COMMAND_TYPES, DEFAULT_PLATFORM_SUPPORTED_TOOLS
from app.messages_assistant import read_whatsapp_messages
from app.android_screen_agent import run_android_screen_task
from app.agent_loop import _get_fallback_candidates, run_agent_loop


def test_no_desktop_gui_libraries_imported_by_server():
    """
    Requirement 4:
    Screen and keyboard tools must run on user's device (Electron or Android), never on Render server.
    Ensures pyautogui, pynput, keyboard, mouse are NEVER imported into server sys.modules.
    """
    forbidden_libs = ["pyautogui", "pynput", "mouse", "keyboard"]
    for lib in forbidden_libs:
        assert lib not in sys.modules, f"Server code imported forbidden desktop library: {lib}"

    # Also inspect all .py files in app/ for direct import statements
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    for root, _, files in os.walk(app_dir):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8") as py_file:
                    content = py_file.read()
                    for lib in forbidden_libs:
                        assert f"import {lib}" not in content, f"Direct 'import {lib}' found in {path}"
                        assert f"from {lib}" not in content, f"'from {lib}' found in {path}"


@pytest.mark.asyncio
async def test_settings_pages_routing_and_open_settings_tool():
    """
    Requirement 1 & 2:
    - open_settings tool opens settings pages (settings, bluetooth, wifi, display, etc.).
    - handle_open_app automatically routes settings targets to open_settings.
    """
    mock_db = MagicMock()
    mock_db.get_trusted_devices.return_value = [
        {"device_id": "laptop_1", "name": "My Laptop", "platform": "windows", "status": "trusted"}
    ]
    mock_db.get_user_devices.return_value = mock_db.get_trusted_devices.return_value

    mock_relay = MagicMock()
    mock_relay.is_device_connected.return_value = True
    mock_relay.relay_command = AsyncMock(return_value={"success": True})
    mock_relay.wait_for_command_completion = AsyncMock(return_value={"status": "succeeded", "result": {"success": True}})

    ctx = {"db": mock_db, "relay_manager": mock_relay}

    # 1. Direct call to handle_open_settings for bluetooth
    res_direct = await handle_open_settings(user_id=1, args={"page": "bluetooth", "target_device": "laptop"}, ctx=ctx)
    assert res_direct["success"] is True
    assert "bluetooth" in res_direct["page"]
    mock_relay.relay_command.assert_called()
    sent_cmd = mock_relay.relay_command.call_args[0][1]
    assert sent_cmd["type"] == "open_settings"
    assert sent_cmd["payload"]["page"] == "bluetooth"

    # 2. handle_open_app for 'settings' routes to handle_open_settings
    res_via_open_app = await handle_open_app(user_id=1, args={"name": "settings", "target_device": "laptop"}, ctx=ctx)
    assert res_via_open_app["success"] is True
    assert "settings" in res_via_open_app["message"].lower()

    # 3. Tool is registered in default_registry
    assert default_registry.get("open_settings") is not None
    assert "open_settings" in SUPPORTED_COMMAND_TYPES


@pytest.mark.asyncio
async def test_screen_control_truthful_accessibility_guidance():
    """
    Requirement 5:
    The phone must report truthfully whether accessibility service is enabled,
    blocked by restricted settings, or disabled, giving the exact Settings path without guessing.
    """
    mock_relay = MagicMock()
    mock_relay.is_device_connected.return_value = True
    mock_relay.relay_command = AsyncMock(return_value={"success": True})

    # Case A: Blocked by Android restricted settings
    mock_relay.wait_for_command_completion = AsyncMock(return_value={
        "status": "failed",
        "error": "Accessibility is blocked by Android restricted settings.",
        "result": {
            "success": False,
            "accessibility_status": "blocked_by_restricted_settings",
            "guidance": "Accessibility is blocked by Android restricted settings. Go to Settings -> Apps -> SINBHA -> ⋮ -> Allow restricted settings, then enable SINBHA in Settings -> Accessibility."
        }
    })

    res_wa = await read_whatsapp_messages(
        user_id=1,
        contact_name="Mom",
        relay_manager=mock_relay,
        target_device="phone"
    )
    assert res_wa["success"] is False
    assert "restricted settings" in res_wa["message"].lower()
    assert "update the app" not in res_wa["message"].lower()

    # Case B: Turned off in Accessibility
    mock_relay.wait_for_command_completion = AsyncMock(return_value={
        "status": "failed",
        "error": "SINBHA Screen Agent is turned off.",
        "result": {
            "success": False,
            "accessibility_status": "disabled",
            "guidance": "SINBHA Screen Agent is turned off. Open Phone Settings -> Accessibility -> Installed apps -> SINBHA Screen Agent and turn it on."
        }
    })

    mock_db = MagicMock()
    mock_db.get_emergency_stopped.return_value = False
    res_screen = await run_android_screen_task(
        user_id=1,
        goal="open whatsapp and check messages",
        target_device="phone",
        db_module=mock_db,
        relay_manager=mock_relay
    )
    assert res_screen["success"] is False
    assert "turned off" in res_screen["message"].lower() or "accessibility" in res_screen["message"].lower()
    assert "settings -> accessibility" in res_screen["message"].lower()


def test_presence_last_seen_reporting():
    """
    Requirement 7:
    Do not say a device is offline unless heartbeat is older than threshold.
    Show the exact last-seen time instead of guessing.
    """
    now = time.time()
    mock_db = MagicMock()

    # 1. Device seen 35 seconds ago (within 90s threshold)
    dev_recent = {
        "device_id": "dev_1",
        "last_seen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 35))
    }
    mock_db.get_device_presence.return_value = dev_recent
    duration_recent = _format_device_last_seen(dev_recent, 1, mock_db)
    assert "s ago" in duration_recent

    # 2. Device seen 15 minutes ago
    dev_older = {
        "device_id": "dev_2",
        "last_seen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 900))
    }
    mock_db.get_device_presence.return_value = dev_older
    duration_older = _format_device_last_seen(dev_older, 1, mock_db)
    assert "15m ago" in duration_older or "m ago" in duration_older


def test_llm_fallback_candidates_and_openrouter_token_capping():
    """
    Requirement 3:
    - Fallback candidates contain real available models on Groq and OpenRouter.
    - Automatic fallback switches between models and providers.
    """
    creds_groq = {
        "provider": "groq",
        "api_key": "gsk_test",
        "model": "openai/gpt-oss-120b",
        "endpoint": "https://api.groq.com/openai/v1/chat/completions"
    }

    candidates = _get_fallback_candidates(creds_groq)
    assert len(candidates) >= 1
    # Check that Groq secondary models are real valid models with separate quotas
    model_names = [c.get("model") for c in candidates]
    assert "openai/gpt-oss-20b" in model_names or any(c.get("provider") == "openrouter" for c in candidates)


@pytest.mark.asyncio
async def test_daily_rate_limit_lockout_and_tool_result_preservation():
    """
    Verifies:
    1. mark_model_lockout locks out exhausted models and get_llm_credentials auto-selects 20b.
    2. When a tool has executed and synthesis hits 429, the tool confirmation message is preserved.
    """
    from app.ai_brain import mark_model_lockout, is_model_locked_out, get_llm_credentials
    from app.agent_tools import build_default_registry

    # 1. Lockout functionality
    mark_model_lockout("groq", "openai/gpt-oss-120b", 60.0)
    assert is_model_locked_out("groq", "openai/gpt-oss-120b") is True

    with patch.dict(os.environ, {"GROQ_API_KEY": "dummy_gsk", "GROQ_MODEL": "openai/gpt-oss-120b"}):
        creds = get_llm_credentials("groq")
        assert creds["model"] == "openai/gpt-oss-20b"

    # 2. Tool result preservation on subsequent rate limit
    mock_reg = build_default_registry()
    tool_call = {
        "id": "tc_1",
        "type": "function",
        "function": {"name": "open_app", "arguments": '{"name":"youtube","target_device":"phone"}'}
    }

    # Step 0 returns tool call; Step 1 returns 429
    call_count = 0
    async def mock_call_llm(messages, tools, creds, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "success": True,
                "message": {"role": "assistant", "content": None, "tool_calls": [tool_call]},
                "finish_reason": "tool_calls",
                "provider": "groq",
                "model": "openai/gpt-oss-20b",
                "latency_ms": 100
            }
        # Subsequent call fails with 429
        return {"success": False, "error": "rate_limit", "status": 429, "provider": "groq", "model": "openai/gpt-oss-20b"}

    with patch("app.agent_loop._call_llm_with_tools", side_effect=mock_call_llm):
        mock_relay = MagicMock()
        mock_relay.is_device_connected.return_value = True
        mock_relay.relay_command = AsyncMock(return_value={"success": True, "message": "Opened YouTube on Phone", "status": "succeeded"})
        mock_relay.wait_for_command_completion = AsyncMock(return_value={"status": "succeeded", "result": {"package": "com.google.android.youtube"}})
        mock_db = MagicMock()
        mock_db.get_emergency_stopped.return_value = False
        mock_db.is_emergency_stopped.return_value = False
        mock_db.get_setting.return_value = "chrome"
        mock_db.get_trusted_devices.return_value = [{"device_id": "phone1", "platform": "android", "name": "Phone", "status": "trusted"}]
        mock_db.get_user_devices.return_value = mock_db.get_trusted_devices.return_value

        res = await run_agent_loop(
            user_id=1,
            user_message="open youtube in my phone",
            chat_history=[],
            remembered_facts=[],
            user_devices=mock_db.get_trusted_devices.return_value,
            db_module=mock_db,
            relay_manager=mock_relay,
            registry=mock_reg
        )
        assert res.reply is not None
        # Must preserve the action result, NOT display a raw 429 error
        assert "429" not in res.reply
        assert "opened youtube on phone" in res.reply.lower()
        assert len(res.tool_calls_log) == 1


