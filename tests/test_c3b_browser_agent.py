"""
Step C3b Test Suite: Managed Chrome with Playwright
Validates:
1. Chrome detection & profile isolation (~/.sinbha/browser_profile, never default profile).
2. Clear SINBHA browser data safety (confirmation required, only deletes isolated profile).
3. The 8 semantic Playwright tools (navigate, click_by_role, click_by_text, type_text, press_key, read_page_text, screenshot, wait_for).
4. Action gating on sensitive actions (buy, pay, submit, book, delete).
5. Safe typing enforcement (blocks passwords, OTPs, credit cards).
6. Untrusted page data and defense against hidden prompt injection (display:none, visibility:hidden, opacity:0).
7. Fact & price verification citations (page URL and timestamp).
8. Worker mode foundations (URL allowlist, encrypted screenshots, dry-run mode).
9. Emergency STOP hook.
"""

import os
import re
import pytest
import asyncio
from pathlib import Path

from app.browser_agent import (
    SinbhaBrowserAgent,
    BrowserTaskConfig,
    find_system_chrome,
    get_sinbha_profile_dir,
    clear_sinbha_browser_data,
    SINBHA_BROWSER_DIR,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_PAGE_URL = (FIXTURES_DIR / "test_page.html").resolve().as_uri()
INJECTION_PAGE_URL = (FIXTURES_DIR / "injection_page.html").resolve().as_uri()


# -----------------------------------------------------------------------------
# 1. PROFILE ISOLATION & CHROME DETECTION
# -----------------------------------------------------------------------------

def test_profile_isolation():
    profile_dir = get_sinbha_profile_dir()
    assert profile_dir == SINBHA_BROWSER_DIR
    assert ".sinbha" in str(profile_dir)
    assert "User Data" not in str(profile_dir) or ".sinbha" in str(profile_dir)
    # Ensure profile path does not touch standard Chrome default user data
    standard_chrome_path = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    assert str(profile_dir).lower() != standard_chrome_path.lower()


def test_find_system_chrome():
    chrome_path = find_system_chrome()
    # On Windows if Chrome is installed, it returns a valid .exe path
    if chrome_path:
        assert Path(chrome_path).exists()
        assert "chrome.exe" in chrome_path.lower()


# -----------------------------------------------------------------------------
# 2. CLEAR BROWSER DATA FLOW
# -----------------------------------------------------------------------------

def test_clear_browser_data_requires_confirmation(tmp_path, monkeypatch):
    test_profile = tmp_path / "sinbha_browser"
    test_profile.mkdir(parents=True)
    dummy_cookie = test_profile / "Cookies.db"
    dummy_cookie.write_text("dummy cookie data")

    monkeypatch.setattr("app.browser_agent.SINBHA_BROWSER_DIR", test_profile)

    # 1. Unconfirmed attempt
    res_unconfirmed = clear_sinbha_browser_data(confirmed=False)
    assert not res_unconfirmed["success"]
    assert res_unconfirmed["needs_user_confirmation"] is True
    assert dummy_cookie.exists()  # Not deleted!

    # 2. Confirmed attempt
    res_confirmed = clear_sinbha_browser_data(confirmed=True)
    assert res_confirmed["success"] is True
    assert not dummy_cookie.exists()  # Safely cleared
    assert test_profile.exists()      # Directory recreated cleanly


# -----------------------------------------------------------------------------
# 3. SEMANTIC PLAYWRIGHT TOOLS ON LOCAL FIXTURE
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_tools_execution():
    config = BrowserTaskConfig(
        headless=True,  # Headless for automated CI/unit tests
        max_steps=20,
        timeout_seconds=30.0,
    )
    agent = SinbhaBrowserAgent(config=config)
    init_res = await agent.initialize()
    if not init_res["success"]:
        pytest.skip(f"Browser launch unavailable in test environment: {init_res.get('error')}")

    try:
        # 1. Navigate
        nav_res = await agent.navigate(TEST_PAGE_URL)
        assert nav_res["success"] is True
        assert "SINBHA Test Store" in nav_res["title"]

        # 2. Read page text and verify price citation
        read_res = await agent.read_page_text()
        assert read_res["success"] is True
        assert "$49.99" in read_res["text"]
        assert "Super Wireless Headphones" in read_res["text"]
        assert read_res["verified_at"] is not None
        assert read_res["is_untrusted_data"] is True

        # 3. Type safe text
        type_res = await agent.type_text("#notes-input", "Gift wrap please")
        assert type_res["success"] is True

        # 4. Press allowlisted key
        press_res = await agent.press_key("Enter")
        assert press_res["success"] is True

        # 5. Click by text (safe action)
        click_res = await agent.click_by_text("Save Notes")
        assert click_res["success"] is True

        # 6. Wait for status confirmation
        wait_res = await agent.wait_for("Notes saved", timeout=2.0)
        assert wait_res["success"] is True

        # 7. Capture screenshot
        shot_res = await agent.screenshot()
        assert shot_res["success"] is True
        assert len(shot_res["base64"]) > 100
    finally:
        await agent.close()


# -----------------------------------------------------------------------------
# 4. ACTION GATING ON SENSITIVE ACTIONS & DRY RUN
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_action_gating_sensitive_buttons():
    config = BrowserTaskConfig(headless=True)
    agent = SinbhaBrowserAgent(config=config)
    init_res = await agent.initialize()
    if not init_res["success"]:
        pytest.skip("Browser launch unavailable")

    try:
        await agent.navigate(TEST_PAGE_URL)

        # "Buy Now" has sensitive verb 'buy' -> Action Gating triggered
        click_buy = await agent.click_by_text("Buy Now")
        assert click_buy["success"] is False
        assert click_buy.get("action_gated") is True
        assert click_buy.get("needs_user_confirmation") is True

        # "Delete Item" has sensitive verb 'delete' -> Action Gating triggered
        click_delete = await agent.click_by_role("button", "Delete Item")
        assert click_delete["success"] is False
        assert click_delete.get("action_gated") is True
    finally:
        await agent.close()


@pytest.mark.asyncio
async def test_dry_run_mode_halts_before_click():
    config = BrowserTaskConfig(headless=True, dry_run=True)
    agent = SinbhaBrowserAgent(config=config)
    init_res = await agent.initialize()
    if not init_res["success"]:
        pytest.skip("Browser launch unavailable")

    try:
        await agent.navigate(TEST_PAGE_URL)

        # In dry run, click is intercepted and simulated without firing DOM event
        click_res = await agent.click_by_text("Add to Cart")
        assert click_res["success"] is True
        assert click_res.get("dry_run") is True
    finally:
        await agent.close()


# -----------------------------------------------------------------------------
# 5. SAFE TYPING ENFORCEMENT
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safe_typing_blocks_secrets():
    config = BrowserTaskConfig(headless=True)
    agent = SinbhaBrowserAgent(config=config)
    init_res = await agent.initialize()
    if not init_res["success"]:
        pytest.skip("Browser launch unavailable")

    try:
        await agent.navigate(TEST_PAGE_URL)

        # Password / secret text blocked
        res_pw = await agent.type_text("#notes-input", "My password is SecretPass123!")
        assert res_pw["success"] is False
        assert "Blocked unsafe typing" in res_pw["error"]

        # Credit card / payment credentials blocked
        res_cc = await agent.type_text("#notes-input", "4111 2222 3333 4444")
        assert res_cc["success"] is False
        assert "Blocked unsafe typing" in res_cc["error"]
    finally:
        await agent.close()


# -----------------------------------------------------------------------------
# 6. UNTRUSTED DATA & HIDDEN PROMPT INJECTION DEFENSE
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hidden_prompt_injection_is_ignored():
    config = BrowserTaskConfig(headless=True)
    agent = SinbhaBrowserAgent(config=config)
    init_res = await agent.initialize()
    if not init_res["success"]:
        pytest.skip("Browser launch unavailable")

    try:
        await agent.navigate(INJECTION_PAGE_URL)
        read_res = await agent.read_page_text()

        assert read_res["success"] is True
        text = read_res["text"]

        # 1. Legitimate visible facts ARE captured
        assert "Flight Booking Portal" in text
        assert "Route: NYC to LON" in text
        assert "$250" in text

        # 2. Hidden injection payloads are COMPLETELY omitted
        assert "Delete all paired devices" not in text
        assert "Transfer $10000" not in text
        assert "P@ssword123" not in text
        assert "attacker@evil.com" not in text

        # 3. Output marked as untrusted
        assert read_res["is_untrusted_data"] is True
    finally:
        await agent.close()


# -----------------------------------------------------------------------------
# 7. WORKER MODE: URL ALLOWLIST & ENCRYPTED SCREENSHOTS
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_worker_mode_url_allowlist_and_encryption():
    config = BrowserTaskConfig(
        headless=True,
        worker_mode=True,
        url_allowlist=["example.com", "verified-domain.org"]
    )
    agent = SinbhaBrowserAgent(config=config)
    init_res = await agent.initialize()
    if not init_res["success"]:
        pytest.skip("Browser launch unavailable")

    try:
        # Blocked domain navigation
        blocked_nav = await agent.navigate("https://malicious-site.com/hack")
        assert blocked_nav["success"] is False
        assert "URL allowlist violation" in blocked_nav["error"]

        # Screenshot encryption in worker mode
        await agent.navigate(TEST_PAGE_URL)  # local file allowed
        shot = await agent.screenshot()
        assert shot["success"] is True
        assert shot.get("encrypted") is True
        assert "ciphertext" in shot
    finally:
        await agent.close()


# -----------------------------------------------------------------------------
# 8. EMERGENCY STOP HOOK
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emergency_stop():
    config = BrowserTaskConfig(headless=True)
    agent = SinbhaBrowserAgent(config=config)
    init_res = await agent.initialize()
    if not init_res["success"]:
        pytest.skip("Browser launch unavailable")

    try:
        agent.stop()
        assert agent.is_stopped is True

        # Next action fails immediately with stopped error
        nav_res = await agent.navigate(TEST_PAGE_URL)
        assert nav_res["success"] is False
        assert "Emergency STOP" in nav_res["error"]
    finally:
        await agent.close()
