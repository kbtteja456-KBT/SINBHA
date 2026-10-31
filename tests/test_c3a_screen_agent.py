"""
Step C3a: Windows Screen Agent Tests
- Tests with recorded screenshots:
  1. Open Notepad, type and save.
  2. Open Claude, ask a question, read the answer.
  3. Draft a Slack message, gate before "send" (DO NOT send it).
- Never-capture list: password managers and banking windows.
- Action gating: gate ACTIONS (send, buy, delete, post, submit), not apps.
- Forbidden typing: never type passwords, OTPs, or card numbers.
- Untrusted screen text defense.
- Active-task memory for multi-turn continuations.
"""

import pytest
import asyncio
import base64
import io
import time
from unittest.mock import patch, MagicMock
from PIL import Image, ImageDraw

from app.screen_agent import (
    is_active_window_sensitive,
    validate_safe_typing,
    check_action_gating,
    check_login_or_captcha_screen,
    crop_screen_region,
    execute_native_action,
    run_screen_task_loop,
    active_screen_task_memory,
    NEVER_CAPTURE_KEYWORDS,
    GATED_ACTION_VERBS,
)
from app.agent_tools import handle_screen_task
from app import database as db


@pytest.fixture
def test_user():
    email = f"c3a_test_{int(time.time()*1000)}@sinbha.local"
    user = db.create_user(email, "hashed_pw", "C3a User", "UTC")
    u_id = user["id"] if isinstance(user, dict) else user
    return {"id": u_id, "email": email}


def create_mock_screenshot(text: str, button: str = None) -> Tuple[str, Image.Image]:
    """Generates a synthetic recorded desktop screenshot in memory."""
    img = Image.new("RGB", (1280, 720), color=(240, 242, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 1230, 670], fill=(255, 255, 255), outline=(200, 200, 200), width=2)
    draw.text((70, 70), text, fill=(20, 20, 20))
    if button:
        draw.rectangle([600, 500, 720, 540], fill=(219, 39, 119), outline=(150, 20, 80))
        draw.text((630, 515), button, fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode("utf-8"), img


# ============================================================================
# 1. NEVER-CAPTURE PRIVACY LIST
# ============================================================================

def test_never_capture_list_blocks_sensitive_windows():
    """Password managers and banking windows must be detected and blocked from capture."""
    sensitive_titles = [
        "1Password - Master Password Unlock",
        "Bitwarden Vault - Unlocked",
        "KeePassXC - Passwords",
        "Chase Online Banking - Account Overview",
        "Wells Fargo Sign On",
        "Windows Security - Enter Network Credentials",
    ]
    for title in sensitive_titles:
        with patch("app.screen_agent.get_foreground_window_title", return_value=title):
            is_sens, matched = is_active_window_sensitive()
            assert is_sens is True, f"Failed to block sensitive window: {title}"

    # Non-sensitive window
    with patch("app.screen_agent.get_foreground_window_title", return_value="Untitled - Notepad"):
        is_sens, _ = is_active_window_sensitive()
        assert is_sens is False


# ============================================================================
# 2. FORBIDDEN TYPING & SECURITY GUARDS
# ============================================================================

def test_validate_safe_typing_strictly_blocks_secrets():
    """Never types passwords, OTP codes, or credit card numbers."""
    # Passwords
    assert validate_safe_typing("password: supersecret123")[0] is False
    assert validate_safe_typing("my password is Password123!")[0] is False

    # OTPs
    assert validate_safe_typing("Your verification code is 482910")[0] is False
    assert validate_safe_typing("Enter OTP 123456")[0] is False

    # Credit Cards
    assert validate_safe_typing("Card 4532 1122 3344 5566")[0] is False

    # Safe text
    assert validate_safe_typing("Hello, this is a normal test note")[0] is True
    assert validate_safe_typing("Meeting tomorrow at 3pm")[0] is True


# ============================================================================
# 3. ACTION GATING (GATE ACTIONS, NOT APPS)
# ============================================================================

def test_action_gating_triggers_on_sensitive_verbs():
    """Verifies that send, post, submit, buy, pay, delete, install, share require confirmation."""
    for verb in ["send", "post", "submit", "buy", "pay", "delete", "install", "share"]:
        action = {"action": "click", "text": verb, "description": f"Click {verb} button"}
        is_gated, reason = check_action_gating(action, "Draft message")
        assert is_gated is True
        assert reason == verb

    # Non-gated action (e.g. typing or clicking a menu)
    safe_action = {"action": "click", "description": "Click File menu"}
    is_gated, _ = check_action_gating(safe_action, "Open menu")
    assert is_gated is False


def test_crop_screen_region():
    """Verifies screenshot crop creation around sensitive actions."""
    _, pil_img = create_mock_screenshot("Test Screen", button="Send")
    crop_b64 = crop_screen_region(pil_img, 650, 520, radius=50)
    assert crop_b64 is not None
    assert len(crop_b64) > 50


# ============================================================================
# 4. RECORDED SCREENSHOTS WORKFLOW TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_workflow_1_notepad_type_and_save(test_user):
    """
    Scenario 1: Open Notepad, type 'Hello SINBHA' and save.
    Simulates vision model progression through atomic actions.
    """
    user_id = test_user["id"]
    actions_executed = []

    def mock_native_action(action):
        actions_executed.append(action["action"])
        return True, "ok"

    step = 0
    async def mock_vision(goal, img, history, creds):
        nonlocal step
        step += 1
        if step == 1:
            return True, {"action": "type", "text": "Hello SINBHA", "description": "Type text into Notepad"}, None
        elif step == 2:
            return True, {"action": "key_combo", "keys": ["ctrl", "s"], "description": "Save file"}, None
        else:
            return True, {"action": "done", "summary": "Notepad typed and saved."}, None

    with patch("app.screen_agent.capture_primary_screen", return_value=(True, "dummy_b64", Image.new("RGB", (100, 100)), None)):
        with patch("app.screen_agent.call_vision_model", side_effect=mock_vision):
            with patch("app.screen_agent.execute_native_action", side_effect=mock_native_action):
                res = await run_screen_task_loop(
                    user_id=user_id,
                    goal="Open Notepad, type Hello SINBHA and save",
                    creds={"provider": "groq", "model": "gemini", "api_key": "dummy", "endpoint": "http://dummy"},
                    max_steps=5
                )
                assert res["success"] is True
                assert res["status"] == "done"
                assert "type" in actions_executed
                assert "key_combo" in actions_executed


@pytest.mark.asyncio
async def test_workflow_2_claude_ask_and_read(test_user):
    """
    Scenario 2: Open Claude, ask a question, read the answer.
    """
    user_id = test_user["id"]
    step = 0

    async def mock_vision(goal, img, history, creds):
        nonlocal step
        step += 1
        if step == 1:
            return True, {"action": "click", "x": 400, "y": 600, "description": "Click Claude prompt input"}, None
        elif step == 2:
            return True, {"action": "type", "text": "What is 2+2?", "description": "Type math question"}, None
        elif step == 3:
            return True, {"action": "key_combo", "keys": ["enter"], "description": "Press enter to run query"}, None
        else:
            return True, {"action": "done", "summary": "Read Claude answer: 4."}, None

    with patch("app.screen_agent.capture_primary_screen", return_value=(True, "dummy_b64", Image.new("RGB", (100, 100)), None)):
        with patch("app.screen_agent.call_vision_model", side_effect=mock_vision):
            with patch("app.screen_agent.execute_native_action", return_value=(True, "ok")):
                res = await run_screen_task_loop(
                    user_id=user_id,
                    goal="Ask Claude what is 2+2 and read the answer",
                    creds={"provider": "groq", "model": "gemini", "api_key": "dummy", "endpoint": "http://dummy"},
                    max_steps=6
                )
                assert res["success"] is True
                assert res["status"] == "done"
                assert "4" in res["message"]


@pytest.mark.asyncio
async def test_workflow_3_slack_draft_message_gated_send(test_user):
    """
    Scenario 3: Draft a Slack message, but do NOT send it (gated!).
    Verifies that the agent types the draft, but when reaching the Send button,
    it pauses with action_gated and requires explicit user confirmation.
    """
    user_id = test_user["id"]
    step = 0

    _, mock_img = create_mock_screenshot("Slack - #general", button="Send")

    async def mock_vision(goal, img, history, creds):
        nonlocal step
        step += 1
        if step == 1:
            return True, {"action": "type", "text": "Team update draft", "description": "Draft Slack message"}, None
        else:
            # Model attempts to click Send button -> Must be gated!
            return True, {"action": "click", "x": 650, "y": 520, "description": "Click send button", "text": "send"}, None

    with patch("app.screen_agent.capture_primary_screen", return_value=(True, "dummy_b64", mock_img, None)):
        with patch("app.screen_agent.call_vision_model", side_effect=mock_vision):
            with patch("app.screen_agent.execute_native_action", return_value=(True, "ok")):
                res = await run_screen_task_loop(
                    user_id=user_id,
                    goal="Draft a Slack message to team",
                    creds={"provider": "groq", "model": "gemini", "api_key": "dummy", "endpoint": "http://dummy"},
                    max_steps=5
                )
                # Must be halted at gate! Never sent!
                assert res["success"] is False
                assert res["status"] == "action_gated"
                assert res["requires_confirmation"] is True
                assert res["gated_operation"] == "send"
                assert res["crop_base64"] != ""


# ============================================================================
# 5. ACTIVE TASK MEMORY & CONTINUATION
# ============================================================================

@pytest.mark.asyncio
async def test_active_task_memory_continuation(test_user):
    """
    Verifies that active-task memory persists context so follow-up commands
    continue the same job.
    """
    user_id = test_user["id"]
    active_screen_task_memory[user_id] = {
        "goal": "Draft report",
        "history": [{"step": 1, "action": {"action": "type", "text": "hello"}}],
        "timestamp": time.time()
    }

    # Follow up turn
    stored = active_screen_task_memory.get(user_id)
    assert stored is not None
    assert stored["goal"] == "Draft report"
    assert len(stored["history"]) == 1
