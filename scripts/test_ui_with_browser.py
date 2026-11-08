"""
SINBHA End-to-End Real Browser UI Test (Safe Isolated Mode)
Uses Playwright to validate:
1. Responsive mobile viewports (360x800, 390x844, 412x915) with zero horizontal overflow
2. Touch target accessibility verification (all interactive targets >= 48x48 CSS px)
3. Form interactions, tab navigation, drawer workflows, and DOM chat response rendering
4. Clean, disposable execution with automatic resource cleanup
"""

import sys
import time
import asyncio
import sqlite3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from playwright.async_api import async_playwright
from scripts.isolated_server_harness import isolated_test_server

SCREENSHOT_PATH = ROOT / "docs" / "ui_live_test.png"
VIEWPORTS = [
    {"name": "Compact Phone (360x800)", "width": 360, "height": 800},
    {"name": "Standard Phone (390x844)", "width": 390, "height": 844},
    {"name": "Large Phone (412x915)", "width": 412, "height": 915},
]


async def run_browser_ui_test():
    print("=" * 65)
    print("🌐 [BROWSER UI TEST] Starting Safe Isolated Playwright Test")
    print("=" * 65)

    with isolated_test_server() as srv:
        base_url = srv["base_url"]
        db_path = srv["db_path"]
        print(f"👉 Running against isolated test server: {base_url}")

        # Seed verified test user in isolated SQLite database
        test_email = f"browser_user_{int(time.time())}@sinbha.local"
        test_password = "BrowserPassword123!"
        
        # Create user via real auth API endpoint on isolated server
        import httpx
        with httpx.Client(timeout=10.0) as client:
            signup_res = client.post(f"{base_url}/api/auth/signup", json={
                "email": test_email,
                "password": test_password,
                "is_18_or_older": True,
                "agree_terms": True
            })
            assert signup_res.status_code == 200, f"Signup failed: {signup_res.text}"
            user_id = signup_res.json()["user"]["id"]

        # Mark user verified in isolated DB and seed initial fact, task & trusted device
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session as OrmSession
        from app.models import User, Device, Fact, Task

        eng = create_engine(f"sqlite:///{db_path}")
        with OrmSession(eng) as s:
            u = s.get(User, user_id)
            if u:
                u.is_verified = True
            dev = Device(
                user_id=user_id,
                device_id="primary_test_device",
                name="Test Web Browser",
                platform="web",
                status="trusted"
            )
            fact = Fact(
                user_id=user_id,
                fact="Studying Computer Architecture and Compilers",
                category="education",
                fact_type="current_goal",
                source="user_explicit",
                confidence=100
            )
            task = Task(
                user_id=user_id,
                title="Complete Pipeline Hazard Simulation",
                due_date="in 2 days"
            )
            s.add_all([dev, fact, task])
            s.commit()

        print(f"👉 Prepared verified test user #{user_id}: {test_email} in isolated DB")

        async with async_playwright() as p:
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            browser = await p.chromium.launch(executable_path=chrome_path, headless=True)

            # -------------------------------------------------------------
            # Part 1: Responsive Viewport & Touch Target Auditing
            # -------------------------------------------------------------
            print("\n" + "=" * 65)
            print("📱 [AUDIT] Checking Touch Targets (>= 48px) and Viewport Overflows")
            print("=" * 65)

            for vp in VIEWPORTS:
                print(f"\n👉 Testing Viewport: {vp['name']} ({vp['width']}x{vp['height']})")
                context = await browser.new_context(viewport={"width": vp["width"], "height": vp["height"]})
                page = await context.new_page()
                await page.goto(base_url, wait_until="domcontentloaded")

                # Verify no horizontal scrollbar/overflow
                overflow = await page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth")
                print(f"   Horizontal Overflow Detected: {overflow}")
                assert not overflow, f"Horizontal overflow detected on viewport {vp['name']}"

                # Wait for auth screen to be visible
                await page.wait_for_selector("#tabSignupBtn", state="visible", timeout=10000)

                # Switch to Signup form to inspect signup touch targets
                await page.click("#tabSignupBtn")
                await page.wait_for_timeout(300)

                # Touch target inspection function
                async def check_target(selector, name, min_w=48, min_h=48):
                    el = await page.query_selector(selector)
                    assert el is not None, f"Element {name} ({selector}) not found"
                    box = await el.bounding_box()
                    assert box is not None, f"Bounding box for {name} ({selector}) is None"
                    w, h = round(box["width"], 1), round(box["height"], 1)
                    print(f"   - {name} [{selector}]: {w}px x {h}px (Required: >={min_w}x{min_h})")
                    assert w >= min_w, f"{name} width {w}px < {min_w}px"
                    assert h >= min_h, f"{name} height {h}px < {min_h}px"

                # Check Auth / Signup Interactive Controls
                await check_target("#signupSubmitBtn", "Create Account Button", min_w=48, min_h=48)
                await check_target(".auth-checkbox-label:has(#signupAgeCheck)", "Age Checkbox Label", min_w=48, min_h=48)
                await check_target(".auth-checkbox-label:has(#signupTermsCheck)", "Terms Checkbox Label", min_w=48, min_h=48)
                await check_target("#openTermsLink", "Terms of Service Link", min_w=48, min_h=48)
                await check_target("#openPrivacyLink", "Privacy Policy Link", min_w=48, min_h=48)

                await context.close()

            # -------------------------------------------------------------
            # Part 2: Interactive App Flow & Navigation Verification
            # -------------------------------------------------------------
            print("\n" + "=" * 65)
            print("🚀 [APP FLOW] Interactive Authentication, Tabs & Live Chat")
            print("=" * 65)

            context = await browser.new_context(viewport={"width": 390, "height": 844})
            page = await context.new_page()
            page.on("console", lambda msg: print(f"   [BROWSER LOG] {msg.text}"))
            page.on("pageerror", lambda err: print(f"   [PAGE ERROR] {err}"))
            await page.goto(base_url, wait_until="domcontentloaded")

            # Fill login form
            print(f"👉 Logging in as {test_email}...")
            await page.wait_for_selector("#tabLoginBtn", state="visible", timeout=10000)
            await page.click("#tabLoginBtn")
            await page.fill("#loginEmail", test_email)
            await page.fill("#loginPassword", test_password)
            await page.click("#loginSubmitBtn")

            # Wait for main chat interface
            await page.wait_for_selector("#messageInput", timeout=15000)
            print("   ✅ Authenticated and entered main app view!")

            # If first-device trust modal appears, dismiss it cleanly
            first_modal = await page.query_selector("#firstDeviceTrustModal")
            if first_modal and await first_modal.is_visible():
                print("   Dismissing first device trust modal...")
                await page.fill("#firstDeviceModalPasswordInput", test_password)
                await page.click("#firstDeviceModalSubmitBtn")
                await page.wait_for_timeout(1000)

            # Verify Bottom Navigation touch targets
            bottom_items = await page.query_selector_all(".bottom-nav-item")
            print(f"👉 Auditing {len(bottom_items)} bottom navigation items for >= 48px target:")
            for idx, item in enumerate(bottom_items):
                box = await item.bounding_box()
                assert box is not None
                w, h = round(box["width"], 1), round(box["height"], 1)
                print(f"   - Bottom Nav Item #{idx + 1}: {w}px x {h}px")
                assert w >= 48 and h >= 48

            # Test Tasks Drawer & Close Button Target
            print("👉 Opening Tasks drawer...")
            await page.click("#navTasksBtn")
            await page.wait_for_selector("#taskDrawer.open, #taskDrawer[aria-hidden='false']", timeout=5000)
            task_close_btn = await page.query_selector("#closeTaskBtn")
            assert task_close_btn is not None
            tc_box = await task_close_btn.bounding_box()
            assert tc_box is not None
            print(f"   - Task Drawer Close Button: {round(tc_box['width'], 1)}px x {round(tc_box['height'], 1)}px")
            assert tc_box["width"] >= 48 and tc_box["height"] >= 48
            await task_close_btn.click()
            await page.wait_for_timeout(300)

            # Test Memory / Settings Modal & Close Button Target
            print("👉 Opening Memory / Settings modal...")
            await page.click("#navMemoryBtn")
            await page.wait_for_selector("#settingsModal", timeout=5000)
            await page.wait_for_timeout(400)  # Wait for scaleInModal animation to complete
            settings_close_btn = await page.query_selector("#closeSettingsBtn")
            assert settings_close_btn is not None
            sc_box = await settings_close_btn.bounding_box()
            assert sc_box is not None
            print(f"   - Settings Modal Close Button: {round(sc_box['width'], 1)}px x {round(sc_box['height'], 1)}px")
            assert sc_box["width"] >= 48 and sc_box["height"] >= 48
            await settings_close_btn.click()
            await page.wait_for_timeout(300)

            # Back to Chat & Dispatch Live Message
            await page.click("#navChatBtn")
            await page.wait_for_timeout(200)

            test_msg = "Hello SINBHA! Tell me my study goals."
            print(f"👉 Sending chat message: \"{test_msg}\"")
            await page.fill("#messageInput", test_msg)
            await page.click("#sendBtn")

            print("👉 Awaiting assistant reply in DOM...")
            await page.wait_for_selector(".message-bubble.ai-bubble", timeout=20000)
            bubbles = await page.query_selector_all(".message-bubble.ai-bubble")
            assert len(bubbles) > 0, "No assistant response bubble rendered"
            reply_text = await bubbles[-1].inner_text()
            print(f"\n💬 [SINBHA LIVE REPLY IN DOM]:\n   \"{reply_text.strip()}\"\n")

            # Capture UI Screenshot into docs/
            SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(SCREENSHOT_PATH))
            print(f"📸 Live screenshot saved to: {SCREENSHOT_PATH}")

            await browser.close()

            print("\n" + "=" * 65)
            print("🎉 ALL REAL BROWSER UI & TOUCH TARGET TESTS PASSED IN ISOLATION!")
            print("=" * 65)
            return True


if __name__ == "__main__":
    success = asyncio.run(run_browser_ui_test())
    sys.exit(0 if success else 1)
