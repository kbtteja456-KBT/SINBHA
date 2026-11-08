"""
Tests for Step 1C Item 5:
Verification that keyword mappings for 'local store', 'our store', and 'test store'
are completely removed from AI tools, and test fixtures are only reachable via explicit URL in DEV_MODE/tests.
"""
import pytest
from unittest.mock import patch
import app.browser_agent
from app.agent_tools import handle_browser_task

@pytest.mark.asyncio
async def test_no_keyword_mapping_for_local_store(setup_test_db):
    """
    Step 1C Item 5: Phrases like 'check the price of headphones on our local store'
    must NOT map to test_page.html fixture.
    """
    with patch("app.browser_agent.run_browser_task") as mock_run:
        mock_run.return_value = {"success": True, "result": "checked"}

        # Goal containing 'our local store' without explicit start_url
        res = await handle_browser_task(
            user_id=1,
            args={"goal": "Check the price of headphones on our local store"},
            ctx={}
        )

        assert res["success"] is True
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        # start_url must be None, NOT mapped to test_page.html
        assert kwargs.get("start_url") is None


@pytest.mark.asyncio
async def test_local_file_fixture_blocked_outside_dev_mode():
    """
    Local file URLs (test fixtures) must be rejected outside DEV_MODE and tests.
    """
    with patch("app.security.is_dev_or_test_env", return_value=False):
        res = await handle_browser_task(
            user_id=1,
            args={
                "goal": "Read catalog",
                "start_url": "file:///C:/secret/path/test_page.html"
            },
            ctx={}
        )
        assert res["success"] is False
        assert "restricted" in res["error"].lower()
