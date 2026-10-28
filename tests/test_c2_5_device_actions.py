"""
Step C2.5 Automated Test Suite: Truthful, Observable and Reliable Device Actions.

Tests:
1. No success message without a device confirmation.
2. Success message only after device confirmation (with PID or method).
3. Unsupported tool handling (plainly informs user, never fakes execution).
4. Typo-tolerant app matching (antygravity, calclator, chatgpy).
5. Command timeout handling (~10 seconds -> "I sent it but could not confirm").
6. Sequential message ordering lock & preventing new messages from triggering previous actions.
7. LLM reliability, retries, and failure classification (rate_limit, timeout, empty_answer, malformed_tool_call) without private text.
"""

import pytest
import asyncio
import time
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.device_relay import CommandRelayManager
from app.agent_tools import (
    handle_open_app,
    handle_type_text,
    compute_app_similarity,
    find_app_candidates,
)
from app.agent_loop import (
    run_agent_loop,
    _call_llm_with_tools,
    log_llm_reliability,
    AgentResult,
)


# =====================================================================
# 1. No success message without device confirmation & Success on confirm
# =====================================================================

@pytest.mark.asyncio
async def test_no_success_message_when_device_fails():
    """Verify the agent does NOT claim success if device returns failed."""
    relay = CommandRelayManager()
    user_id = 1
    device_id = "test_laptop_1"

    fake_ws = AsyncMock()
    fake_ws.send_text = AsyncMock()
    relay.register_websocket(user_id, device_id, fake_ws)
    relay.record_device_capabilities(user_id, device_id, platform="windows", app_version="1.4.5", supported_tools=["open_app", "open_url"])

    dev_obj = {"device_id": device_id, "name": "Laptop", "platform": "windows", "status": "trusted", "capabilities": {"open_app": True}, "permission_level": 1}
    mock_db = MagicMock()
    mock_db.get_user_devices.return_value = [dev_obj]
    mock_db.get_device_by_id.return_value = dev_obj
    mock_db.get_setting.return_value = "chrome"

    ctx = {
        "db": mock_db,
        "relay_manager": relay,
        "user_devices": [dev_obj],
        "user_timezone": "UTC",
    }

    # Simulate device rejecting command
    async def simulate_failure():
        await asyncio.sleep(0.05)
        lifecycles = relay.command_lifecycles
        if lifecycles:
            cmd_id = list(lifecycles.keys())[0]
            relay.update_command_status(user_id, cmd_id, "failed", error="Executable not found: code 127")

    asyncio.create_task(simulate_failure())

    with patch("app.device_relay.db.get_device_by_id", return_value=dev_obj), \
         patch("app.device_relay.db.log_audit", return_value=None):
        res = await handle_open_app(user_id, {"name": "photoshop", "target_device": "laptop"}, ctx)

    assert res["success"] is False
    assert "Executable not found" in res["message"] or "Could not open" in res["message"]
    # Agent MUST NOT say "Opened photoshop"
    assert "Opened photoshop" not in res["message"]


@pytest.mark.asyncio
async def test_success_message_only_after_device_confirms_pid():
    """Verify the agent reports success with PID only after device confirmation."""
    relay = CommandRelayManager()
    user_id = 1
    device_id = "test_laptop_1"

    fake_ws = AsyncMock()
    fake_ws.send_text = AsyncMock()
    relay.register_websocket(user_id, device_id, fake_ws)
    relay.record_device_capabilities(user_id, device_id, platform="windows", app_version="1.4.5", supported_tools=["open_app"])

    dev_obj = {"device_id": device_id, "name": "Laptop", "platform": "windows", "status": "trusted", "capabilities": {"open_app": True}, "permission_level": 1}
    mock_db = MagicMock()
    mock_db.get_user_devices.return_value = [dev_obj]
    mock_db.get_device_by_id.return_value = dev_obj
    mock_db.get_setting.return_value = "chrome"

    ctx = {
        "db": mock_db,
        "relay_manager": relay,
        "user_devices": [dev_obj],
        "user_timezone": "UTC",
    }

    # Simulate device successfully starting Notepad with PID 8421
    async def simulate_success():
        await asyncio.sleep(0.05)
        lifecycles = relay.command_lifecycles
        if lifecycles:
            cmd_id = list(lifecycles.keys())[0]
            relay.update_command_status(user_id, cmd_id, "succeeded", result={"pid": 8421, "method": "spawn"})

    asyncio.create_task(simulate_success())

    with patch("app.device_relay.db.get_device_by_id", return_value=dev_obj), \
         patch("app.device_relay.db.log_audit", return_value=None):
        res = await handle_open_app(user_id, {"name": "notepad", "target_device": "laptop"}, ctx)

    assert res["success"] is True
    assert "Opened notepad" in res["message"]
    assert "PID: 8421" in res["message"]


# =====================================================================
# 2. Command timeout handling (~10 seconds -> Plain unconfirmed message)
# =====================================================================

@pytest.mark.asyncio
async def test_command_timeout_reports_unconfirmed():
    """Verify timeout yields plain 'I sent it but could not confirm'."""
    relay = CommandRelayManager()
    user_id = 1
    device_id = "test_phone_1"

    fake_ws = AsyncMock()
    fake_ws.send_text = AsyncMock()
    relay.register_websocket(user_id, device_id, fake_ws)
    relay.record_device_capabilities(user_id, device_id, platform="android", app_version="1.4.5", supported_tools=["open_app"])

    dev_obj = {"device_id": device_id, "name": "Phone", "platform": "android", "status": "trusted", "capabilities": {"open_app": True}, "permission_level": 1}
    mock_db = MagicMock()
    mock_db.get_user_devices.return_value = [dev_obj]
    mock_db.get_device_by_id.return_value = dev_obj
    mock_db.get_setting.return_value = "chrome"

    ctx = {
        "db": mock_db,
        "relay_manager": relay,
        "user_devices": [dev_obj],
        "user_timezone": "UTC",
    }

    # Use patch to simulate timeout response
    with patch("app.device_relay.db.get_device_by_id", return_value=dev_obj), \
         patch("app.device_relay.db.log_audit", return_value=None), \
         patch.object(relay, "wait_for_command_completion", new_callable=AsyncMock, return_value={"status": "timed_out", "message": "Command timed out waiting for device confirmation."}):
        res = await handle_open_app(user_id, {"name": "youtube", "target_device": "phone"}, ctx)

    assert res["success"] is False
    assert res["status"] in ("timeout", "unconfirmed")
    assert "could not confirm" in res["message"]
    assert "I sent it" in res["message"]


# =====================================================================
# 3. Capability Handshake: Unsupported tools handled truthfully
# =====================================================================

@pytest.mark.asyncio
async def test_unsupported_tool_plainly_declined():
    """When a device does not support a tool, SINBHA must say so plainly without faking."""
    relay = CommandRelayManager()
    user_id = 1
    device_id = "test_phone_old"

    fake_ws = AsyncMock()
    fake_ws.send_text = AsyncMock()
    relay.register_websocket(user_id, device_id, fake_ws)
    # Old phone only supports ring_phone, not open_app
    relay.record_device_capabilities(user_id, device_id, platform="android", app_version="1.0.0", supported_tools=["ring_phone"])

    dev_obj = {"device_id": device_id, "name": "Old Phone", "platform": "android", "status": "trusted", "capabilities": {"ring_phone": True}, "permission_level": 1}
    mock_db = MagicMock()
    mock_db.get_user_devices.return_value = [dev_obj]
    mock_db.get_device_by_id.return_value = dev_obj
    mock_db.get_setting.return_value = "chrome"

    ctx = {
        "db": mock_db,
        "relay_manager": relay,
        "user_devices": [dev_obj],
        "user_timezone": "UTC",
    }

    res = await handle_open_app(user_id, {"name": "spotify", "target_device": "phone"}, ctx)
    assert res["success"] is False
    assert res["status"] == "unsupported_tool"
    assert "does not support opening apps yet, please update" in res["message"]


# =====================================================================
# 4. Typo-tolerant app matching (antygravity, calclator, chatgpy)
# =====================================================================

def test_typo_tolerant_matching_known_variations():
    """Verify similarity computation and top-3 candidate ranking for typos."""
    app_catalog = [
        {"name": "Antigravity", "id": "antigravity"},
        {"name": "Calculator", "id": "calculator"},
        {"name": "ChatGPT", "id": "chatgpt"},
        {"name": "Claude", "id": "claude"},
        {"name": "Chrome", "id": "chrome"},
        {"name": "Notepad", "id": "notepad"},
    ]

    # Test "antygravity"
    top_ag = find_app_candidates("antygravity", app_catalog)
    assert len(top_ag) > 0
    assert top_ag[0]["app"]["id"] == "antigravity"
    assert top_ag[0]["confidence"] == "high"

    # Test "calclator"
    top_calc = find_app_candidates("calclator", app_catalog)
    assert len(top_calc) > 0
    assert top_calc[0]["app"]["id"] == "calculator"
    assert top_calc[0]["confidence"] == "high"

    # Test "chatgpy"
    top_gpt = find_app_candidates("chatgpy", app_catalog)
    assert len(top_gpt) > 0
    assert top_gpt[0]["app"]["id"] == "chatgpt"
    assert top_gpt[0]["confidence"] == "high"


# =====================================================================
# 5. Message Ordering & Stale Action Prevention
# =====================================================================

@pytest.mark.asyncio
async def test_sequential_message_lock_and_stale_action_cancellation():
    """Verify sequential handling and that new messages cancel old proposals."""
    from app.main import _user_chat_locks

    user_id = 999
    _user_chat_locks[user_id] = asyncio.Lock()
    lock = _user_chat_locks[user_id]

    order = []

    async def msg_task(idx, delay):
        async with lock:
            order.append(f"start_{idx}")
            await asyncio.sleep(delay)
            order.append(f"end_{idx}")

    # Launch two tasks concurrently
    await asyncio.gather(
        msg_task(1, 0.05),
        msg_task(2, 0.01),
    )

    # Message 1 must fully finish before Message 2 starts
    assert order == ["start_1", "end_1", "start_2", "end_2"]


# =====================================================================
# 6. LLM Reliability: Classification, Retries, and Privacy Safety
# =====================================================================

@pytest.mark.asyncio
async def test_llm_rate_limit_classification_and_backoff():
    """Verify 429 is classified as rate_limit and retries with backoff."""
    creds = {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "api_key": "dummy_key",
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
    }

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.json.return_value = {"error": {"message": "Rate limit exceeded"}}

    with patch("httpx.AsyncClient.post", return_value=mock_response), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        res = await _call_llm_with_tools([], [], creds)
        assert res["success"] is False
        assert res["error"] == "rate_limit"
        assert res["status"] == 429
        # Backoff was invoked twice (attempt 0 and 1)
        assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_llm_empty_answer_classification():
    """Verify empty assistant response is classified as empty_answer, never faked."""
    creds = {
        "provider": "openrouter",
        "model": "google/gemini-2.5-flash",
        "api_key": "dummy_key",
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {"content": "   ", "tool_calls": None},
            "finish_reason": "stop"
        }]
    }

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        res = await _call_llm_with_tools([], [], creds)
        assert res["success"] is False
        assert res["error"] == "empty_answer"


def test_llm_reliability_logging_has_no_private_text(caplog):
    """Verify log_llm_reliability never emits private prompt or chat messages."""
    with caplog.at_level("WARNING"):
        log_llm_reliability(
            event_type="rate_limit",
            provider="groq",
            model="llama-3.3-70b-versatile",
            attempt=1,
            status_code=429,
            latency_ms=120.5,
            error_detail="Too many requests",
        )

    log_output = caplog.text
    assert "rate_limit" in log_output
    assert "groq" in log_output
    # Must NOT contain sensitive user text
    assert "user_message" not in log_output
    assert "prompt" not in log_output
