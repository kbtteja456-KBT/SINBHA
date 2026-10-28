"""
Unit and integration tests for Step C2: Laptop Tools (Desktop App Index, Browsers, Keys, Tracking).
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from app.agent_tools import (
    default_registry,
    validate_safe_typing_text,
    _resolve_target_device,
    ALLOWED_KEY_COMBINATIONS,
    handle_open_app,
    handle_type_text,
    handle_press_keys,
    handle_find_installed_app,
)


class TestC2SchemasAndRegistry:
    def test_c2_tools_registered(self):
        c2_tools = ["find_installed_app", "open_app", "type_text", "press_keys"]
        for tool_name in c2_tools:
            tool = default_registry.get(tool_name)
            assert tool is not None, f"Tool {tool_name} not registered"

    def test_c2_risk_levels(self):
        assert default_registry.get("find_installed_app").risk_level == 0
        assert default_registry.get("open_app").risk_level == 2
        assert default_registry.get("type_text").risk_level == 2
        assert default_registry.get("press_keys").risk_level == 2

    def test_open_url_browser_parameter(self):
        open_url_tool = default_registry.get("open_url")
        # Valid browser values
        assert open_url_tool.validate_args({"url": "https://example.com", "browser": "chrome"}) == []
        assert open_url_tool.validate_args({"url": "https://example.com", "browser": "edge"}) == []
        assert open_url_tool.validate_args({"url": "https://example.com", "browser": "firefox"}) == []
        assert open_url_tool.validate_args({"url": "https://example.com", "browser": "default"}) == []

        # Invalid browser
        errs = open_url_tool.validate_args({"url": "https://example.com", "browser": "safari"})
        assert len(errs) > 0


class TestC2TypingSafetyGuard:
    def test_password_blocking(self):
        bad_texts = [
            "password: SecretPassword123",
            "My password is pass123",
            "secret = abcdef",
            "passcode: 9876",
        ]
        for t in bad_texts:
            safe, err = validate_safe_typing_text(t)
            assert not safe, f"Should have blocked password in: {t}"
            assert "password" in err.lower() or "secret" in err.lower()

    def test_otp_blocking(self):
        bad_texts = [
            "Your verification OTP is 492819",
            "Enter the 6-digit code: 123456",
            "Here is your auth code: 987654",
            "My security pin is 4321",
        ]
        for t in bad_texts:
            safe, err = validate_safe_typing_text(t)
            assert not safe, f"Should have blocked OTP in: {t}"
            assert "otp" in err.lower() or "pin" in err.lower()

    def test_payment_and_credit_card_blocking(self):
        bad_texts = [
            "Card 4532 0152 8392 1029 CVV 123",
            "pay $50 to seller",
            "checkout now and make payment",
            "send money via wire transfer",
        ]
        for t in bad_texts:
            safe, err = validate_safe_typing_text(t)
            assert not safe, f"Should have blocked payment in: {t}"
            assert "card" in err.lower() or "payment" in err.lower()

    def test_normal_text_allowed(self):
        good_texts = [
            "Can you write a summary of the meeting?",
            "Hello world!",
            "Search for best pasta recipes in Italy",
            "Python 3.12 documentation",
        ]
        for t in good_texts:
            safe, _ = validate_safe_typing_text(t)
            assert safe, f"Should have allowed safe text: {t}"


class TestC2KeysValidation:
    def test_allowlisted_keys(self):
        valid_keys = ["enter", "tab", "esc", "space", "backspace", "ctrl+c", "ctrl+v", "alt+tab", "f5"]
        for k in valid_keys:
            assert k in ALLOWED_KEY_COMBINATIONS

    def test_disallowed_keys(self):
        invalid_keys = ["ctrl+alt+del", "win+r", "cmd", "powershell", "format c:"]
        for k in invalid_keys:
            assert k not in ALLOWED_KEY_COMBINATIONS


class TestC2DeviceResolution:
    def test_resolve_laptop_by_name_and_category(self):
        devices = [
            {"device_id": "lap_1", "name": "Workstation Laptop", "platform": "windows"},
            {"device_id": "ph_1", "name": "Pixel 8", "platform": "android"},
        ]
        # By category
        res = _resolve_target_device(devices, "laptop", None, 1)
        assert res["status"] == "ok"
        assert res["device"]["device_id"] == "lap_1"

        # By explicit name
        res_name = _resolve_target_device(devices, "Pixel 8", None, 1)
        assert res_name["status"] == "ok"
        assert res_name["device"]["device_id"] == "ph_1"

    def test_resolve_ambiguous_devices(self):
        devices = [
            {"device_id": "ph_1", "name": "Pixel 8", "platform": "android"},
            {"device_id": "ph_2", "name": "Galaxy S24", "platform": "android"},
            {"device_id": "lap_1", "name": "ThinkPad", "platform": "windows"},
        ]
        # Ambiguous phone request: user has 2 phones and asks for "phone"
        res = _resolve_target_device(devices, "phone", None, 1)
        assert res["status"] == "ambiguous"
        assert len(res["candidates"]) == 2
        assert "Which device" in res["message"]


@pytest.mark.asyncio
class TestC2ToolExecution:
    async def test_open_app_with_preferred_browser(self):
        mock_db = MagicMock()
        mock_db.get_setting.return_value = "edge"
        mock_db.get_user_devices.return_value = [
            {"device_id": "lap_1", "name": "Dell Laptop", "platform": "windows", "status": "trusted"}
        ]
        mock_relay = AsyncMock()

        ctx = {"db": mock_db, "relay_manager": mock_relay}
        res = await handle_open_app(1, {"name": "claude", "target_device": "laptop"}, ctx)

        assert res["success"] is True
        assert res["browser"] == "edge"
        assert res["app"] == "claude"

    async def test_open_app_with_explicit_browser(self):
        mock_db = MagicMock()
        mock_db.get_setting.return_value = "chrome"
        mock_db.get_user_devices.return_value = [
            {"device_id": "lap_1", "name": "Dell Laptop", "platform": "windows", "status": "trusted"}
        ]
        mock_relay = AsyncMock()

        ctx = {"db": mock_db, "relay_manager": mock_relay}
        res = await handle_open_app(1, {"name": "youtube", "browser": "firefox"}, ctx)

        assert res["success"] is True
        assert res["browser"] == "firefox"

    async def test_type_text_blocks_credentials(self):
        mock_db = MagicMock()
        mock_relay = AsyncMock()
        ctx = {"db": mock_db, "relay_manager": mock_relay}

        res = await handle_type_text(1, {"text": "password: admin123"}, ctx)
        assert res["success"] is False
        assert "password" in res["error"].lower()

    async def test_press_keys_allowlist_enforced(self):
        mock_db = MagicMock()
        mock_relay = AsyncMock()
        ctx = {"db": mock_db, "relay_manager": mock_relay}

        res = await handle_press_keys(1, {"keys": "ctrl+alt+del"}, ctx)
        assert res["success"] is False
        assert "not allowlisted" in res["error"]
