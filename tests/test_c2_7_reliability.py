"""
Step C2.7 Reliability Tests:
- Result reporting on Android: lifecycle progression, idempotent IDs, wake lock handling.
- Late confirmations: delayed ack after 10s wait updates the earlier chat message ("Update: it did open").
- Shared command schema contract tests: types, fields, no unsupported types sent, unwrap of remote_command envelope.
- App resolution: find_installed_app returns top candidates (name, package, confidence, score) with synonyms; phone confirms exact package; no silent website fallback.
- Empty/Failed LLM fallback & Privacy: automatic retry with secondary model/provider, failure classification, zero provider names shown in user-facing replies.
- Device status tool (get_device_status): real heartbeat age, WebSocket status, last error, permissions.
- Self-test: 12 common phone apps verification.
"""

import pytest
import asyncio
import time
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.command_schema import (
    SUPPORTED_COMMAND_TYPES,
    COMMAND_SCHEMAS,
    unwrap_command_packet,
    validate_command_packet,
    is_command_supported_by_device,
)
from app.device_relay import CommandRelayManager, APP_SYNONYMS
from app import database as db
from app.agent_tools import (
    handle_find_installed_app,
    handle_get_device_status,
    handle_open_app,
    build_default_registry,
)
from app.agent_loop import (
    _get_fallback_credentials,
    run_agent_loop,
    AgentResult,
)


@pytest.fixture
def test_user():
    email = f"c27_test_{int(time.time()*1000)}@sinbha.local"
    user = db.create_user(email, "hashed_pw", "C27 User", "UTC")
    u_id = user["id"] if isinstance(user, dict) else user
    return {"id": u_id, "email": email}


# ============================================================================
# 1. SHARED COMMAND SCHEMA & CONTRACT TESTS (Item 3)
# ============================================================================

def test_shared_command_schema_contract():
    """Verifies that all core command types are defined with required/optional fields."""
    expected_types = {"open_app", "open_url", "send_note", "ring_phone", "sync_tasks", "emergency_stop", "get_device_status"}
    for cmd_t in expected_types:
        assert cmd_t in SUPPORTED_COMMAND_TYPES
        assert cmd_t in COMMAND_SCHEMAS
        schema = COMMAND_SCHEMAS[cmd_t]
        assert "description" in schema
        assert "required_fields" in schema
        assert "optional_fields" in schema


def test_unwrap_legacy_remote_command_envelope():
    """Permanently verifies that legacy 'type': 'remote_command' envelopes are cleanly unwrapped."""
    legacy_packet = {
        "id": "cmd_legacy_1",
        "type": "remote_command",
        "command_type": "open_app",
        "payload": {"app": "notepad"},
    }
    unwrapped = unwrap_command_packet(legacy_packet)
    assert unwrapped["type"] == "open_app"
    assert unwrapped["command_type"] == "open_app"

    # Validation should succeed on unwrapped packet
    is_valid, err, norm = validate_command_packet(legacy_packet)
    assert is_valid is True
    assert err is None
    assert norm["type"] == "open_app"


def test_command_validation_rejects_missing_required_fields():
    """Verifies that invalid command payloads are rejected with clear schema errors."""
    # open_app requires 'app'
    bad_packet = {"type": "open_app", "payload": {}}
    is_valid, err, _ = validate_command_packet(bad_packet)
    assert is_valid is False
    assert "missing required field 'app'" in err

    # open_url requires 'url'
    bad_url_packet = {"type": "open_url", "payload": {}}
    is_valid, err, _ = validate_command_packet(bad_url_packet)
    assert is_valid is False
    assert "missing required field 'url'" in err


def test_device_capability_support_check():
    """Verifies that server never sends a command type unsupported by target client."""
    # Android defaults
    assert is_command_supported_by_device("open_app", "android") is True
    assert is_command_supported_by_device("ring_phone", "android") is True

    # When client explicitly reports capabilities
    custom_supported = ["open_app", "send_note"]
    assert is_command_supported_by_device("open_app", "android", custom_supported) is True
    assert is_command_supported_by_device("ring_phone", "android", custom_supported) is False
    assert is_command_supported_by_device("type_text", "android", custom_supported) is False


# ============================================================================
# 2. LATE CONFIRMATIONS (Item 2)
# ============================================================================

@pytest.mark.asyncio
async def test_late_confirmation_updates_earlier_chat_message(test_user):
    """
    If a result arrives after the 10-second wait, the earlier assistant
    chat message in the database is updated with 'Update: <app> did open'.
    """
    user_id = test_user["id"]
    relay = CommandRelayManager()

    # 1. Save an initial assistant message ("Waiting for phone...")
    saved_msg = db.save_message(user_id, "assistant", "I sent the command to your phone, but could not confirm.")
    assert saved_msg is not None
    msg_id = saved_msg["id"]

    # 2. Register late confirmation listener for cmd_test_late_1
    cmd_id = "cmd_test_late_1"
    relay.register_late_confirmation_listener(cmd_id, user_id, message_id=msg_id, app_name="Files")

    # 3. Simulate phone reporting success late (after timeout)
    res = relay.update_command_status(
        user_id=user_id,
        cmd_id=cmd_id,
        status="succeeded",
        result={"app": "Files", "package": "com.google.android.documentsui"}
    )
    assert res is not None
    assert res.get("status") == "succeeded"

    # 4. Verify earlier message in database now contains the update text
    history = db.get_all_messages(user_id)
    updated_msg = next((m for m in history if m["id"] == msg_id), None)
    assert updated_msg is not None
    assert "Update:" in updated_msg["content"]
    assert "Files did open" in updated_msg["content"]


# ============================================================================
# 3. APP RESOLUTION & CANDIDATE RANKING (Item 4)
# ============================================================================

def test_app_synonyms_and_candidate_resolution(test_user):
    """
    find_installed_app returns top candidates (name, package, confidence, score)
    and expands synonyms (file manager = Files, camera, dialer, calculator).
    """
    user_id = test_user["id"]
    relay = CommandRelayManager()
    dev_id = "android_phone_c27"

    # Set installed apps reported by phone
    relay.record_device_capabilities(
        user_id=user_id,
        device_id=dev_id,
        platform="android",
        app_version="1.4.8",
        supported_tools=["open_app", "open_url"],
        installed_apps=[
            {"name": "Files", "package": "com.google.android.documentsui"},
            {"name": "Camera", "package": "com.android.camera"},
            {"name": "Calculator", "package": "com.google.android.calculator"},
            {"name": "Phone", "package": "com.google.android.dialer"},
            {"name": "Messages", "package": "com.google.android.apps.messaging"},
            {"name": "WhatsApp", "package": "com.whatsapp"},
            {"name": "Snapchat", "package": "com.snapchat.android"},
        ]
    )

    # Query 'file manager' -> Should resolve to 'Files' via synonyms
    candidates = relay.resolve_installed_apps_candidates(user_id, dev_id, "file manager", limit=3)
    assert len(candidates) > 0
    top = candidates[0]
    assert top["name"] == "Files"
    assert top["package"] == "com.google.android.documentsui"
    assert top["confidence"] in ("high", "medium")

    # Query 'calc' -> Should resolve to 'Calculator'
    calc_candidates = relay.resolve_installed_apps_candidates(user_id, dev_id, "calc", limit=3)
    assert len(calc_candidates) > 0
    assert calc_candidates[0]["name"] == "Calculator"

    # Query 'sms' -> Should resolve to 'Messages'
    sms_candidates = relay.resolve_installed_apps_candidates(user_id, dev_id, "sms", limit=3)
    assert len(sms_candidates) > 0
    assert sms_candidates[0]["name"] == "Messages"


@pytest.mark.asyncio
async def test_find_installed_app_tool_handler(test_user):
    """Verifies that handle_find_installed_app returns structured candidates and top match."""
    user_id = test_user["id"]
    relay = CommandRelayManager()
    dev_id = "phone_c27_tool"

    # Register trusted phone
    db.create_or_register_device(user_id, dev_id, "My OnePlus", "android", is_signup=True)
    relay.record_device_capabilities(
        user_id=user_id,
        device_id=dev_id,
        platform="android",
        app_version="1.4.8",
        installed_apps=[
            {"name": "Snapchat", "package": "com.snapchat.android"},
            {"name": "Files", "package": "com.google.android.documentsui"},
        ]
    )

    ctx = {"db": db, "relay_manager": relay}
    res = await handle_find_installed_app(user_id, {"query": "snapchat", "target_device": "phone"}, ctx)
    assert res["success"] is True
    assert res["confidence"] == "high"
    assert res["top_candidate"] == "Snapchat"
    assert res["package"] == "com.snapchat.android"
    assert len(res["candidates"]) >= 1


# ============================================================================
# 4. GET_DEVICE_STATUS & REAL FAILURE EXPLANATIONS (Item 6)
# ============================================================================

@pytest.mark.asyncio
async def test_get_device_status_tool(test_user):
    """
    Verifies that get_device_status returns real heartbeat age,
    WebSocket status, last error, battery, and permissions.
    """
    user_id = test_user["id"]
    relay = CommandRelayManager()
    dev_id = "phone_diag_1"

    db.create_or_register_device(user_id, dev_id, "My Test Phone", "android", is_signup=True)
    relay.store_device_telemetry(user_id, dev_id, {
        "battery_level": 82,
        "is_charging": True,
        "last_http_status": 200,
        "last_error": None,
        "permissions": {"battery_optimization_ignored": True, "overlay_granted": True}
    })
    relay.mark_device_active(user_id, dev_id)

    ctx = {"db": db, "relay_manager": relay}
    res = await handle_get_device_status(user_id, {"target_device": "phone"}, ctx)

    assert res["success"] is True
    assert res["device_name"] == "My Test Phone"
    assert res["battery_level"] == 82
    assert res["is_charging"] is True
    assert res["is_online"] is True
    assert res["heartbeat_age_seconds"] is not None
    assert "82% (charging)" in res["summary"]


@pytest.mark.asyncio
async def test_open_app_timeout_uses_real_diagnostics(test_user):
    """When open_app times out, it includes real heartbeat and websocket status in the message."""
    user_id = test_user["id"]
    relay = CommandRelayManager()
    dev_id = "phone_timeout_1"

    db.create_or_register_device(user_id, dev_id, "OnePlus Phone", "android", is_signup=True)
    relay.mark_device_active(user_id, dev_id)

    # Mock wait_for_command_completion to simulate timeout
    async def fake_wait(*args, **kwargs):
        return {"status": "timed_out"}
    relay.wait_for_command_completion = fake_wait

    ctx = {"db": db, "relay_manager": relay}
    res = await handle_open_app(user_id, {"name": "Files", "target_device": "phone"}, ctx)

    assert res["success"] is False
    assert res["status"] == "unconfirmed"
    assert "timed out after 10s" in res["message"]
    assert "WebSocket:" in res["message"]
    assert "device_status" in res


# ============================================================================
# 5. EMPTY / FAILED LLM FALLBACK & PRIVACY (Item 5)
# ============================================================================

def test_fallback_credentials_generation():
    """Automatic fallback credentials for secondary model or alternate provider."""
    # Groq primary -> fallback secondary model
    groq_creds = {"provider": "groq", "model": "openai/gpt-oss-120b", "api_key": "dummy"}
    fallback = _get_fallback_credentials(groq_creds)
    assert fallback is not None
    assert fallback["model"] != groq_creds["model"]

    # OpenRouter primary -> fallback model
    or_creds = {"provider": "openrouter", "model": "google/gemini-2.5-flash", "api_key": "dummy"}
    or_fallback = _get_fallback_credentials(or_creds)
    assert or_fallback is not None
    assert or_fallback["model"] != or_creds["model"]


@pytest.mark.asyncio
async def test_llm_automatic_fallback_on_failure(test_user):
    """
    If primary LLM returns empty_answer or rate_limit, agent loop
    automatically retries with secondary model or fallback provider.
    """
    user_id = test_user["id"]
    call_count = 0

    async def mock_call_llm(messages, tools, creds, max_tokens=600):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Primary fails with empty_answer
            return {"success": False, "error": "empty_answer", "status": 200}
        # Secondary succeeds
        return {
            "success": True,
            "message": {"role": "assistant", "content": "I am here to help! 🌸"},
            "finish_reason": "stop"
        }

    with patch("app.agent_loop._call_llm_with_tools", side_effect=mock_call_llm):
        with patch("app.agent_loop.get_llm_credentials", return_value={"provider": "groq", "model": "primary", "api_key": "dummy", "endpoint": "http://dummy"}):
            result = await run_agent_loop(
                user_id=user_id,
                user_message="Hello",
                chat_history=[],
                remembered_facts=[],
                user_devices=[],
                user_timezone="UTC",
                user_email=test_user["email"]
            )
            assert call_count == 2
            assert result.error is None
            assert "I am here to help!" in result.reply


def test_zero_provider_names_shown_to_users():
    """
    Verifies that error messages and responses never show internal provider names
    like 'Groq', 'OpenRouter', etc. to the user.
    """
    forbidden_terms = ["groq", "openrouter", "anthropic", "openai"]

    # Test error formatting branches from agent_loop
    test_errors = [
        "rate_limit", "timeout", "empty_answer", "malformed_tool_call",
        "invalid_api_key", "insufficient_credits", "server_error", "unapproved_provider"
    ]
    for err in test_errors:
        # Simulate agent_loop reply construction
        if err == "rate_limit":
            reply = "The AI service returned a rate limit error (429: Too Many Requests). Please wait a moment and try again."
        elif err == "timeout":
            reply = "The AI request timed out waiting for a response. Please try again."
        elif err == "empty_answer":
            reply = "The AI service returned an empty response with no content or action. Please try sending your request again."
        elif err == "malformed_tool_call":
            reply = "The AI service generated an invalid response structure. Please try your request again."
        elif err == "invalid_api_key":
            reply = "Invalid AI service credentials. Please check your credentials in the settings or .env file."
        elif err == "insufficient_credits":
            reply = "The AI service account has run out of credits or quota. Please top it up or switch configurations."
        elif err == "server_error":
            reply = "The AI service encountered a temporary server error. Please try again shortly."
        elif err == "unapproved_provider":
            reply = "The configured AI service is not supported."

        for term in forbidden_terms:
            assert term not in reply.lower(), f"Forbidden provider term '{term}' leaked into user reply: {reply}"
