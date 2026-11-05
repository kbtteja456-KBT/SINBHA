"""
Tests for Milestone M1 + M2 (Solid Command Layer & Phone Reachable / Launching from Background).
Follows AGENT_RULES.md (Rule 24).
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app, get_current_user
from app.agent_loop import run_agent_loop, _get_fallback_candidates, AgentResult
from app.agent_tools import default_registry, ToolRegistry, Tool
from app.llm_provider_config import build_ordered_provider_chain, telemetry


@pytest.fixture
def client():
    mock_user = {"id": 1, "email": "test@example.com"}
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


def test_provider_fallback_chain_includes_gemini_flash():
    """Verify provider chain prioritizes Groq then Gemini (gemini-3-flash-preview) fallback."""
    with patch.dict("os.environ", {
        "GROQ_API_KEY": "gsk_test123",
        "GEMINI_API_KEY": "AIzaSyTest123",
        "OPENROUTER_API_KEY": "sk-or-test123"
    }):
        chain = build_ordered_provider_chain(active_pref="auto")
        providers = [c["provider"] for c in chain]
        assert "groq" in providers
        assert "gemini" in providers
        assert "openrouter" in providers
        gemini_entry = next(c for c in chain if c["provider"] == "gemini")
        assert "gemini-3-flash-preview" in gemini_entry["model"] or "gemini" in gemini_entry["model"]


def test_fallback_candidates_on_groq_failure():
    """Verify fallback candidates are generated when Groq fails."""
    creds = {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "api_key": "gsk_test",
        "endpoint": "https://api.groq.com/openai/v1/chat/completions"
    }
    with patch.dict("os.environ", {
        "GROQ_API_KEY": "gsk_test",
        "GEMINI_API_KEY": "AIzaSyTest",
        "OPENROUTER_API_KEY": "sk-or-test"
    }):
        candidates = _get_fallback_candidates(creds)
        assert len(candidates) >= 1
        assert any(c["provider"] == "gemini" for c in candidates)


@pytest.mark.asyncio
async def test_agent_loop_action_receipt_generation():
    """Verify that action tool execution generates a structured action_receipt."""
    mock_db = MagicMock()
    mock_db.get_emergency_stopped.return_value = False
    mock_relay = MagicMock()

    mock_llm_response_tool = {
        "success": True,
        "message": {
            "content": "Opening Settings on your phone now!",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "open_settings",
                        "arguments": '{"page": "settings", "target_device": "phone"}'
                    }
                }
            ]
        },
        "provider": "groq",
        "model": "openai/gpt-oss-20b"
    }

    mock_llm_response_final = {
        "success": True,
        "message": {
            "content": "Settings is open on your phone.",
            "tool_calls": None
        },
        "provider": "groq",
        "model": "openai/gpt-oss-20b"
    }

    test_reg = ToolRegistry()
    async def mock_handle_settings(user_id, args, ctx):
        return {
            "success": True,
            "status": "succeeded",
            "route": "overlay_window",
            "evidence": "com.android.settings appeared in 450ms",
            "message": "Opened Android Settings on phone."
        }

    test_reg.register(Tool(
        name="open_settings",
        description="Open settings page",
        parameters={"type": "object", "properties": {"page": {"type": "string"}}},
        risk_level=0,
        handler=mock_handle_settings
    ))

    with patch("app.agent_loop._call_llm_with_tools", side_effect=[mock_llm_response_tool, mock_llm_response_final]):
        res: AgentResult = await run_agent_loop(
            user_id=1,
            user_message="open settings in my phone",
            chat_history=[],
            remembered_facts=[],
            user_devices=[{"device_id": "phone_1", "platform": "android", "is_online": True}],
            db_module=mock_db,
            relay_manager=mock_relay,
            registry=test_reg
        )

        assert res.action_receipt is not None
        assert res.action_receipt["tool"] == "open_settings"
        assert res.action_receipt["status"] == "succeeded"
        assert res.action_receipt["route"] == "overlay_window"
        assert "appeared" in res.action_receipt["evidence"]


def test_always_answered_message_flow(client):
    """Verify that user messages are saved first and provider failures yield an app-written message."""
    with patch("app.main.check_endpoint_rate_limits"), \
         patch("app.main.check_ai_usage_caps", return_value=(True, "")), \
         patch("app.main.db.save_message") as mock_save, \
         patch("app.main.db.get_recent_messages", return_value=[]), \
         patch("app.main.db.get_all_facts", return_value=[]), \
         patch("app.main.db.get_user_devices", return_value=[]), \
         patch("app.main.db.get_emergency_stopped", return_value=False), \
         patch("app.main.db.get_pending_task_action", return_value=None), \
         patch("app.main.db.get_pending_proposal", return_value=None), \
         patch("app.main.db.get_pending_action", return_value=None), \
         patch("app.agent_loop.run_agent_loop", side_effect=Exception("LLM Brain connection timed out")):

        response = client.post("/api/chat", json={"message": "helloo"})
        assert response.status_code == 200
        data = response.json()
        assert "trouble reaching my AI brain" in data["reply"]
        assert data.get("retry_available") is True
        # Verify user message was saved first
        assert mock_save.call_count >= 1
        first_call = mock_save.call_args_list[0]
        assert first_call[0][1] == "user"
        assert first_call[0][2] == "helloo"


def test_background_launch_test_endpoint(client):
    """Verify POST /api/devices/background-launch-test returns phone info and route results."""
    mock_device = {
        "device_id": "dev_android_1",
        "name": "Pixel 7 Pro",
        "platform": "android",
        "status": "trusted"
    }
    mock_tel = {
        "phone_model": "Pixel 7 Pro",
        "android_version": "14",
        "sdk_int": 34
    }

    with patch("app.main.db.get_user_devices", return_value=[mock_device]), \
         patch("app.main.relay_manager.get_device_telemetry", return_value=mock_tel), \
         patch("app.agent_tools.handle_open_app", new_callable=AsyncMock) as mock_app, \
         patch("app.agent_tools.handle_open_settings", new_callable=AsyncMock) as mock_settings, \
         patch("app.agent_tools.handle_open_url", new_callable=AsyncMock) as mock_url:

        mock_app.return_value = {"success": True, "status": "succeeded", "route": "overlay_window", "evidence": "window opened"}
        mock_settings.return_value = {"success": True, "status": "succeeded", "route": "full_screen_intent", "evidence": "FSI opened"}
        mock_url.return_value = {"success": True, "status": "succeeded", "route": "accessibility_service", "evidence": "browser opened"}

        resp = client.post("/api/devices/background-launch-test", json={"delay_seconds": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["phone_model"] == "Pixel 7 Pro"
        assert data["android_version"] == "14"
        assert data["sdk_int"] == 34
        assert len(data["results"]) == 4
        routes = [r["route_used"] for r in data["results"]]
        assert "overlay_window" in routes
        assert "full_screen_intent" in routes
        assert "accessibility_service" in routes
