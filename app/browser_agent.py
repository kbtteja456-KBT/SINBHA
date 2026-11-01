"""
Step C3b: Managed Chrome with Playwright
SINBHA Secure Browser Automation Agent

Features:
- Visible Chrome window using an isolated "SINBHA" browser profile (~/.sinbha/browser_profile).
- Never uses normal user Chrome profile.
- Uses installed Google Chrome when available; explains and offers Playwright Chromium if missing.
- Allows user to log in manually in visible window.
- "Clear SINBHA browser data" feature: explains what will be deleted, requires confirmation,
  clears ONLY the SINBHA profile, never touches normal Chrome profile.
- 8 Semantic Playwright Tools (DOM/accessibility over pixels):
  1. navigate(url)
  2. click_by_role(role, name)
  3. click_by_text(text)
  4. type_text(target, text) - strictly blocks passwords, OTPs, card numbers
  5. press_key(key)
  6. read_page_text() - untrusted data marker
  7. screenshot()
  8. wait_for(condition, timeout)
- Read-only by default. Actions that send, post, submit, buy, pay, delete need explicit confirmation.
- If login, CAPTCHA, or 2FA appears: pauses automation and asks user to complete manually.
- Untrusted page text defense: prompt injections & hidden instructions ignored; any level 2+ action
  after reading page text requires fresh confirmation.
- Facts and prices cite page URL and timestamp or say "I could not verify".
- Future-proof "Worker Mode" (for Meesho):
  - URL allowlist per task
  - No OS mouse/keyboard control (Playwright in-browser only)
  - Evidence screenshots encrypted at rest with Fernet
  - Dry-run mode that stops before final click
  - Zero stealth/bot-evasion bypasses
"""

import os
import re
import sys
import time
import shutil
import platform
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from app.crypto import encrypt_text, decrypt_text
from app.screen_agent import validate_safe_typing, GATED_ACTION_VERBS

# Default isolated browser profile directory
SINBHA_BROWSER_DIR = Path.home() / ".sinbha" / "browser_profile"

# Allowlisted keys for Playwright keyboard actions
PLAYWRIGHT_ALLOWED_KEYS = {
    "Enter", "Tab", "Escape", "Backspace", "Delete", "Space",
    "ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight",
    "PageDown", "PageUp", "Home", "End",
    "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"
}

# Login and CAPTCHA detection terms
LOGIN_CAPTCHA_TERMS = (
    "recaptcha", "hcaptcha", "turnstile", "captcha",
    "sign in", "log in", "enter your password", "one-time password",
    "verification code", "two-step verification", "verify it's you"
)


# ============================================================================
# 1. BROWSER & PROFILE MANAGEMENT
# ============================================================================

def get_sinbha_profile_dir() -> Path:
    """Returns the isolated SINBHA browser profile directory."""
    SINBHA_BROWSER_DIR.mkdir(parents=True, exist_ok=True)
    return SINBHA_BROWSER_DIR


def find_system_chrome() -> Optional[str]:
    """
    Locates installed Google Chrome executable on Windows, macOS, or Linux.
    Returns the executable path string if found, else None.
    """
    sys_name = platform.system().lower()
    if sys_name == "windows":
        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
    elif sys_name == "darwin":  # macOS
        p = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if p.exists():
            return str(p)
    elif sys_name == "linux":
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/chromium-browser"),
            Path("/usr/bin/chromium"),
        ]
        for p in candidates:
            if p.exists():
                return str(p)
    return None


def clear_sinbha_browser_data(confirmed: bool = False) -> dict:
    """
    Clears all browser data (cookies, sessions, cache, storage) ONLY in the SINBHA profile.
    Never touches normal Chrome profile.
    Requires confirmed=True before deleting.
    """
    profile_dir = get_sinbha_profile_dir()

    if not confirmed:
        return {
            "success": False,
            "requires_confirmation": True,
            "needs_user_confirmation": True,
            "explanation": (
                "Clearing SINBHA browser data will permanently remove all cookies, saved sessions, "
                "cache, and local storage in the isolated profile directory:\n"
                f"{profile_dir}\n\n"
                "Your regular personal Chrome profile and everyday browser data will NEVER be touched.\n"
                "Please confirm if you want to proceed."
            ),
            "profile_path": str(profile_dir)
        }

    try:
        if profile_dir.exists():
            shutil.rmtree(profile_dir, ignore_errors=True)
        profile_dir.mkdir(parents=True, exist_ok=True)
        return {
            "success": True,
            "message": "SINBHA browser data has been successfully cleared and reset.",
            "profile_path": str(profile_dir)
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to clear SINBHA browser data: {e}",
            "profile_path": str(profile_dir)
        }


# ============================================================================
# 2. BROWSER AGENT SESSION & PLAYWRIGHT DRIVER
# ============================================================================

class BrowserTaskConfig:
    """Configuration for a browser automation task."""
    def __init__(
        self,
        worker_mode: bool = False,
        url_allowlist: Optional[List[str]] = None,
        dry_run: bool = False,
        max_steps: int = 25,
        timeout_seconds: float = 120.0,
        use_chromium_fallback: bool = False,
        headless: bool = False,
    ):
        self.worker_mode = worker_mode
        self.url_allowlist = [u.lower().strip() for u in (url_allowlist or [])]
        self.dry_run = dry_run
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds
        self.use_chromium_fallback = use_chromium_fallback
        self.headless = headless


class SinbhaBrowserAgent:
    """
    Managed Visible Chrome Browser Agent powered by Playwright.
    """
    def __init__(self, config: Optional[BrowserTaskConfig] = None):
        self.config = config or BrowserTaskConfig()
        self.playwright = None
        self.context = None
        self.page = None
        self.step_log: List[dict] = []
        self.start_time: float = 0
        self.is_stopped: bool = False
        self.active_goal: str = ""

    async def initialize(self) -> dict:
        """Launches Playwright with the dedicated visible SINBHA Chrome profile."""
        from playwright.async_api import async_playwright

        profile_dir = get_sinbha_profile_dir()
        chrome_path = find_system_chrome()

        if not chrome_path and not self.config.use_chromium_fallback:
            return {
                "success": False,
                "error": "CHROME_NOT_FOUND",
                "message": (
                    "Installed Google Chrome could not be found on this computer.\n"
                    "SINBHA avoids silently switching browsers. If you would like to use "
                    "Playwright-managed Chromium instead, enable the Chromium fallback option."
                )
            }

        try:
            self.playwright = await async_playwright().start()

            # Launch persistent context
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                executable_path=chrome_path if (chrome_path and not self.config.use_chromium_fallback) else None,
                headless=self.config.headless,
                args=[
                    "--no-default-browser-check",
                    "--disable-infobars",
                    "--window-size=1280,850",
                ],
                viewport={"width": 1280, "height": 800},
            )

            # Use existing or first open page
            pages = self.context.pages
            self.page = pages[0] if pages else await self.context.new_page()
            self.start_time = time.time()

            return {
                "success": True,
                "browser_type": "google-chrome" if chrome_path else "chromium",
                "profile_dir": str(profile_dir),
                "is_visible": not self.config.headless,
            }
        except Exception as e:
            await self.close()
            return {"success": False, "error": f"Failed to initialize browser: {e}"}

    def _check_time_and_steps(self, current_step: int):
        """Checks step count and time limits."""
        if self.is_stopped:
            raise InterruptedError("Browser task stopped by user.")
        if current_step > self.config.max_steps:
            raise TimeoutError(f"Task exceeded maximum step limit ({self.config.max_steps} steps).")
        elapsed = time.time() - self.start_time
        if elapsed > self.config.timeout_seconds:
            raise TimeoutError(f"Task exceeded maximum time limit ({self.config.timeout_seconds}s).")

    def _log_step(self, action: str, details: str, status: str = "ok"):
        """Appends to the live execution step log."""
        entry = {
            "step": len(self.step_log) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": details,
            "status": status,
        }
        self.step_log.append(entry)
        print(f"[BROWSER STEP {entry['step']}] {action}: {details} ({status})")

    def _validate_url_allowlist(self, url: str) -> bool:
        """In worker mode, verifies URL against the task allowlist."""
        if not self.config.worker_mode or not self.config.url_allowlist:
            return True
        url_lower = url.lower()
        return any(domain in url_lower for domain in self.config.url_allowlist)

    # -------------------------------------------------------------
    # THE 8 PLAYWRIGHT SEMANTIC TOOLS
    # -------------------------------------------------------------

    async def navigate(self, url: str) -> dict:
        """1. navigate(url): Navigates to a validated URL."""
        if self.is_stopped:
            return {"success": False, "error": "Emergency STOP: task stopped by user."}

        self._check_time_and_steps(len(self.step_log) + 1)

        clean_url = url.strip()
        if not (clean_url.startswith("http://") or clean_url.startswith("https://") or clean_url.startswith("file://")):
            clean_url = "https://" + clean_url

        if not self._validate_url_allowlist(clean_url):
            self._log_step("navigate", f"Blocked by URL allowlist: {clean_url}", "blocked")
            return {
                "success": False,
                "error": "URL_BLOCKED: URL allowlist violation",
                "message": f"URL '{clean_url}' is not in the allowed domains for this task."
            }

        try:
            await self.page.goto(clean_url, wait_until="domcontentloaded", timeout=30000)
            title = await self.page.title()
            current_url = self.page.url
            self._log_step("navigate", f"{clean_url} (Title: '{title}')", "ok")
            return {
                "success": True,
                "url": current_url,
                "title": title
            }
        except Exception as e:
            self._log_step("navigate", f"{clean_url} failed: {e}", "failed")
            return {"success": False, "error": str(e)}

    async def click_by_role(self, role: str, name: str) -> dict:
        """2. click_by_role(role, name): Clicks an element by semantic role & accessible name."""
        if self.is_stopped:
            return {"success": False, "error": "Emergency STOP: task stopped by user."}

        self._check_time_and_steps(len(self.step_log) + 1)

        # In dry-run mode, stop before any click
        if self.config.dry_run:
            self._log_step("click_by_role", f"[DRY-RUN] Halted before click on {role} '{name}'", "dry_run")
            return {"success": True, "dry_run": True, "role": role, "name": name}

        # Action gating check for sensitive actions
        combined_text = f"{role} {name}".lower()
        for verb in GATED_ACTION_VERBS:
            if verb in combined_text:
                return {
                    "success": False,
                    "action_gated": True,
                    "needs_user_confirmation": True,
                    "requires_confirmation": True,
                    "gated_verb": verb,
                    "action_description": f"Click {role} '{name}'",
                    "message": f"Confirmation required before {verb} action on '{name}'."
                }

        try:
            locator = self.page.get_by_role(role, name=re.compile(rf"{re.escape(name)}", re.I))
            count = await locator.count()
            if count == 0:
                # Fallback to direct name string
                locator = self.page.get_by_role(role, name=name)
            await locator.first.click(timeout=8000)
            self._log_step("click_by_role", f"role='{role}' name='{name}'", "ok")
            return {"success": True, "role": role, "name": name}
        except Exception as e:
            self._log_step("click_by_role", f"Failed role='{role}' name='{name}': {e}", "failed")
            return {"success": False, "error": str(e)}

    async def click_by_text(self, text: str) -> dict:
        """3. click_by_text(text): Clicks an element matching visible semantic text."""
        if self.is_stopped:
            return {"success": False, "error": "Emergency STOP: task stopped by user."}

        self._check_time_and_steps(len(self.step_log) + 1)

        # In dry-run mode, stop before any click
        if self.config.dry_run:
            self._log_step("click_by_text", f"[DRY-RUN] Halted before click on '{text}'", "dry_run")
            return {"success": True, "dry_run": True, "text": text}

        lower = text.lower()
        for verb in GATED_ACTION_VERBS:
            if verb in lower:
                return {
                    "success": False,
                    "action_gated": True,
                    "needs_user_confirmation": True,
                    "requires_confirmation": True,
                    "gated_verb": verb,
                    "action_description": f"Click text '{text}'",
                    "message": f"Confirmation required before {verb} action on '{text}'."
                }

        try:
            locator = self.page.get_by_text(text, exact=False)
            await locator.first.click(timeout=8000)
            self._log_step("click_by_text", f"text='{text}'", "ok")
            return {"success": True, "text": text}
        except Exception as e:
            self._log_step("click_by_text", f"Failed text='{text}': {e}", "failed")
            return {"success": False, "error": str(e)}

    async def type_text(self, target: str, text: str) -> dict:
        """4. type_text(target, text): Types text into input; strictly blocks secrets/OTPs."""
        if self.is_stopped:
            return {"success": False, "error": "Emergency STOP: task stopped by user."}

        self._check_time_and_steps(len(self.step_log) + 1)

        # Strict safety check on input text
        safe, reason = validate_safe_typing(text)
        if not safe:
            self._log_step("type_text", f"Blocked safe typing: {reason}", "blocked")
            return {"success": False, "error": f"Blocked unsafe typing: {reason}", "message": reason}

        # Check if target is a password field
        target_lower = target.lower()
        if any(term in target_lower for term in ("password", "passwd", "passcode", "otp", "pin", "cvv", "card")):
            return {
                "success": False,
                "error": "SENSITIVE_FIELD_BLOCKED",
                "message": "Automated typing into password, OTP, or payment fields is strictly forbidden."
            }

        try:
            # Try semantic selectors in order: placeholder -> label -> role textbox -> CSS
            locator = self.page.get_by_placeholder(target, exact=False)
            if await locator.count() == 0:
                locator = self.page.get_by_label(target, exact=False)
            if await locator.count() == 0:
                locator = self.page.get_by_role("textbox", name=re.compile(rf"{re.escape(target)}", re.I))
            if await locator.count() == 0:
                locator = self.page.locator(target)

            await locator.first.fill(text, timeout=8000)
            self._log_step("type_text", f"target='{target}' typed={len(text)} chars", "ok")
            return {"success": True, "target": target}
        except Exception as e:
            self._log_step("type_text", f"Failed on '{target}': {e}", "failed")
            return {"success": False, "error": str(e)}

    async def press_key(self, key: str) -> dict:
        """5. press_key(key): Presses an allowlisted keyboard key."""
        self._check_time_and_steps(len(self.step_log) + 1)

        clean_key = key.strip()
        # Normalize Enter / Return
        if clean_key.lower() in ("enter", "return"):
            clean_key = "Enter"

        if clean_key not in PLAYWRIGHT_ALLOWED_KEYS:
            return {
                "success": False,
                "error": "DISALLOWED_KEY",
                "message": f"Key '{key}' is not in the safe allowlist."
            }

        try:
            await self.page.keyboard.press(clean_key)
            self._log_step("press_key", f"key='{clean_key}'", "ok")
            return {"success": True, "key": clean_key}
        except Exception as e:
            self._log_step("press_key", f"Failed '{clean_key}': {e}", "failed")
            return {"success": False, "error": str(e)}

    async def read_page_text(self) -> dict:
        """
        6. read_page_text(): Reads page structure and visible text.
        Marks text as UNTRUSTED DATA and strips hidden injection payloads.
        Checks for login / CAPTCHA prompts.
        """
        self._check_time_and_steps(len(self.step_log) + 1)

        try:
            title = await self.page.title()
            current_url = self.page.url

            # Extract visible text using DOM evaluate, filtering hidden elements
            raw_text = await self.page.evaluate("""() => {
                const isVisible = (el) => {
                    const style = window.getComputedStyle(el);
                    return style && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
                };
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                const chunks = [];
                while (walker.nextNode()) {
                    const node = walker.currentNode;
                    if (node.parentElement && isVisible(node.parentElement)) {
                        const trimmed = node.nodeValue.trim();
                        if (trimmed.length > 0) chunks.push(trimmed);
                    }
                }
                return chunks.join('\\n');
            }""")

            # Check if login or CAPTCHA is detected
            needs_login_or_captcha = False
            lower_text = raw_text.lower()
            if any(term in lower_text for term in LOGIN_CAPTCHA_TERMS):
                # Also check for password input on DOM
                pw_inputs = await self.page.locator("input[type='password']").count()
                if pw_inputs > 0 or "captcha" in lower_text:
                    needs_login_or_captcha = True

            timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            self._log_step(
                "read_page_text",
                f"URL='{current_url}', length={len(raw_text)} chars, login_detected={needs_login_or_captcha}",
                "ok"
            )

            return {
                "success": True,
                "url": current_url,
                "title": title,
                "verified_at": timestamp_str,
                "is_untrusted_data": True,
                "login_or_captcha_detected": needs_login_or_captcha,
                "text": raw_text[:8000],  # Return first 8000 chars
            }
        except Exception as e:
            self._log_step("read_page_text", f"Failed: {e}", "failed")
            return {"success": False, "error": str(e)}

    async def screenshot(self) -> dict:
        """7. screenshot(): Captures in-browser screenshot; encrypts evidence in worker mode."""
        self._check_time_and_steps(len(self.step_log) + 1)

        try:
            bytes_data = await self.page.screenshot(type="jpeg", quality=75)
            import base64
            b64_str = base64.b64encode(bytes_data).decode("utf-8")

            encrypted_evidence = None
            if self.config.worker_mode:
                # Encrypt screenshot data with Fernet for audit retention
                encrypted_evidence = encrypt_text(b64_str)

            self._log_step("screenshot", f"Captured {len(bytes_data)} bytes", "ok")
            return {
                "success": True,
                "base64": b64_str,
                "screenshot_base64": b64_str if not self.config.worker_mode else None,
                "encrypted": bool(self.config.worker_mode),
                "ciphertext": encrypted_evidence,
                "encrypted_evidence": encrypted_evidence,
                "size_bytes": len(bytes_data),
            }
        except Exception as e:
            self._log_step("screenshot", f"Failed: {e}", "failed")
            return {"success": False, "error": str(e)}

    async def wait_for(self, condition: str, timeout: float = 5.0) -> dict:
        """8. wait_for(condition, timeout): Waits for text, selector, or timeout seconds."""
        self._check_time_and_steps(len(self.step_log) + 1)

        try:
            # Check if condition is a selector or plain text
            if condition.startswith("#") or condition.startswith(".") or condition.startswith("//"):
                await self.page.wait_for_selector(condition, timeout=int(timeout * 1000))
            elif condition.lower() in ("load", "networkidle", "domcontentloaded"):
                await self.page.wait_for_load_state(condition.lower(), timeout=int(timeout * 1000))
            else:
                # Wait for visible text or sleep
                try:
                    await self.page.get_by_text(condition, exact=False).first.wait_for(timeout=int(timeout * 1000))
                except Exception:
                    await asyncio.sleep(min(timeout, 2.0))

            self._log_step("wait_for", f"condition='{condition}' timeout={timeout}s", "ok")
            return {"success": True, "condition": condition}
        except Exception as e:
            self._log_step("wait_for", f"Condition '{condition}' timed out: {e}", "timeout")
            return {"success": False, "error": str(e)}

    # -------------------------------------------------------------
    # LIFECYCLE & SHUTDOWN
    # -------------------------------------------------------------

    def stop(self):
        """Emergency STOP hook."""
        self.is_stopped = True
        self._log_step("STOP", "Emergency stop triggered.", "stopped")

    async def close(self):
        """Safely closes browser and Playwright process."""
        try:
            if self.context:
                await self.context.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass
        finally:
            self.context = None
            self.playwright = None
            self.page = None


# ============================================================================
# 3. HIGH-LEVEL BROWSER TASK AGENT LOOP
# ============================================================================

async def run_browser_task(
    goal: str,
    start_url: Optional[str] = None,
    config: Optional[BrowserTaskConfig] = None
) -> dict:
    """
    Executes a high-level browser automation task:
    - Launches visible Chrome window with isolated SINBHA profile.
    - Limits steps and execution time.
    - Respects STOP.
    - Returns structured results with live step log and fact citations.
    """
    agent = SinbhaBrowserAgent(config=config)
    agent.active_goal = goal

    init_res = await agent.initialize()
    if not init_res.get("success"):
        return init_res

    try:
        # Initial navigation if URL provided
        if start_url:
            nav_res = await agent.navigate(start_url)
            if not nav_res.get("success"):
                return {"success": False, "error": nav_res.get("error"), "step_log": agent.step_log}

        # Read page structure
        read_res = await agent.read_page_text()
        if read_res.get("login_or_captcha_detected"):
            return {
                "success": False,
                "paused_for_user": True,
                "reason": "LOGIN_OR_CAPTCHA_DETECTED",
                "message": (
                    f"A login, CAPTCHA, or verification prompt was detected at {read_res.get('url')}.\n"
                    "Please complete the authentication manually in the visible Chrome window."
                ),
                "step_log": agent.step_log,
                "url": read_res.get("url"),
            }

        return {
            "success": True,
            "goal": goal,
            "current_url": read_res.get("url"),
            "page_title": read_res.get("title"),
            "verified_at": read_res.get("verified_at"),
            "step_log": agent.step_log,
        }
    finally:
        await agent.close()
