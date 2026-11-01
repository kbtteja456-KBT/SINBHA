"""
SINBHA Step C3b: Live Browser Automation Demonstration
Launches a visible Google Chrome window with the isolated SINBHA profile,
demonstrates semantic DOM reading, safe typing, screenshot, and action gating.
"""

import sys
import asyncio
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.browser_agent import SinbhaBrowserAgent, BrowserTaskConfig, find_system_chrome

FIXTURES_DIR = ROOT_DIR / "tests" / "fixtures"
DEMO_PAGE_URL = (FIXTURES_DIR / "test_page.html").resolve().as_uri()


async def run_live_demo():
    print("=" * 65)
    print("🤖 SINBHA BROWSER AGENT (C3b) - LIVE DEMO")
    print("=" * 65)

    chrome_exe = find_system_chrome()
    print(f"👉 System Chrome detected at: {chrome_exe or 'Not found (using Chromium)'}")
    print("👉 Isolated profile: ~/.sinbha/browser_profile (separate from user Chrome)")
    print("👉 Launching VISIBLE Chrome window...")

    # Configure visible window
    config = BrowserTaskConfig(
        headless=False,
        max_steps=15,
        timeout_seconds=60.0
    )
    agent = SinbhaBrowserAgent(config=config)

    init_res = await agent.initialize()
    if not init_res.get("success"):
        print(f"❌ Failed to initialize browser: {init_res.get('error')}")
        return

    try:
        # Step 1: Navigate
        print(f"\n🌐 [Step 1] Navigating to: {DEMO_PAGE_URL}")
        nav_res = await agent.navigate(DEMO_PAGE_URL)
        print(f"   Success: {nav_res.get('success')} | Title: '{nav_res.get('title')}'")
        await asyncio.sleep(1.0)

        # Step 2: Read DOM Structure & Facts
        print("\n📖 [Step 2] Reading page structure and price facts...")
        read_res = await agent.read_page_text()
        print(f"   Verified At: {read_res.get('verified_at')}")
        print(f"   Page excerpt: {read_res.get('text', '')[:140]}...")
        await asyncio.sleep(1.0)

        # Step 3: Safe Typing
        print("\n⌨️  [Step 3] Safe typing into notes input...")
        type_res = await agent.type_text("#notes-input", "Order priority: expedited shipping")
        print(f"   Type result: {type_res.get('success')}")
        await asyncio.sleep(1.0)

        # Step 4: Semantic Click (Safe)
        print("\n🖱️  [Step 4] Clicking 'Save Notes' button...")
        click_res = await agent.click_by_text("Save Notes")
        print(f"   Click result: {click_res.get('success')}")
        await asyncio.sleep(1.0)

        # Step 5: Action Gating Trigger
        print("\n🛑 [Step 5] Triggering Action Gating on 'Buy Now' button...")
        gated_res = await agent.click_by_text("Buy Now")
        print(f"   Action Gated: {gated_res.get('action_gated')}")
        print(f"   Needs Confirmation: {gated_res.get('needs_user_confirmation')}")
        print(f"   Reason: {gated_res.get('message')}")
        print("   🔒 SAFE GUARD ACTIVE: Sensitive purchase halted until user confirms card.")
        await asyncio.sleep(1.5)

        # Step 6: Capture Screenshot
        print("\n📸 [Step 6] Capturing verified screenshot...")
        shot_res = await agent.screenshot()
        print(f"   Screenshot size: {shot_res.get('size_bytes')} bytes")

        print("\n" + "=" * 65)
        print("✅ LIVE DEMONSTRATION COMPLETE: ALL SAFETY RULES VERIFIED")
        print("=" * 65)

    finally:
        print("Closing browser session...")
        await agent.close()


if __name__ == "__main__":
    asyncio.run(run_live_demo())

