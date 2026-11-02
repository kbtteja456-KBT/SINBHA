import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.version import parse_semver, is_client_version_supported, MIN_COMPATIBLE_CLIENT_VERSION
from app.device_relay import CommandRelayManager
from app.search import execute_web_search
from app.agent_tools import (
    handle_open_app,
    handle_open_url,
    handle_type_text,
    handle_press_keys,
    handle_send_note,
    handle_ring_phone
)
from app.main import app, get_current_user
from httpx import AsyncClient, ASGITransport

class TestC29VersionCheck:
    def test_parse_semver(self):
        assert parse_semver("1.4.21") == (1, 4, 21)
        assert parse_semver("v1.4.21") == (1, 4, 21)
        assert parse_semver("2.0.0-beta") == (2, 0, 0)
        assert parse_semver("invalid") == (0, 0, 0)

    def test_is_client_version_supported(self):
        assert is_client_version_supported("1.4.21") is True
        assert is_client_version_supported("1.5.0") is True
        assert is_client_version_supported("1.4.20") is False
        assert is_client_version_supported("1.0.0") is False
        # Web fallback without version defaults to True
        assert is_client_version_supported(None) is True

    @pytest.mark.asyncio
    async def test_relay_rejects_outdated_client_version(self):
        relay = CommandRelayManager()
        outdated_dev = {
            "device_id": "laptop_old",
            "name": "My Laptop",
            "platform": "windows",
            "client_version": "1.4.19",
            "status": "trusted"
        }
        with patch("app.device_relay.db.is_user_verified", return_value=True), \
             patch("app.device_relay.db.get_emergency_stopped", return_value=False), \
             patch("app.device_relay.db.get_device_by_id", return_value=outdated_dev), \
             patch("app.device_relay.db.log_audit"):
            res = await relay.relay_command(
                user_id=1,
                cmd_data={
                    "id": "cmd_ver_123",
                    "sender_device": "server",
                    "target_device": "laptop_old",
                    "type": "open_app",
                    "payload": {"app": "notepad"}
                }
            )
            assert res.get("status") == "CLIENT_OUTDATED" or res.get("error") == "CLIENT_OUTDATED"
            assert res.get("success") is False
            err_msg = (res.get("error") or "") + " " + (res.get("message") or "")
            assert "please update your app" in err_msg.lower()


class TestC29NoUnconditionalFallbacks:
    @pytest.mark.asyncio
    async def test_tools_return_unconfirmed_on_no_response(self):
        mock_relay = MagicMock()
        mock_relay.relay_command = AsyncMock(return_value={"id": "cmd_123", "status": "sent"})
        mock_relay.wait_for_command_completion = AsyncMock(return_value=None)
        mock_relay.is_device_connected = MagicMock(return_value=True)
        mock_relay.get_device_supported_tools = MagicMock(return_value=["open_app", "open_url", "type_text", "press_keys", "send_note", "ring_phone"])

        mock_db = MagicMock()
        mock_db.get_user_devices.return_value = [
            {"device_id": "laptop_1", "platform": "windows", "status": "trusted", "client_version": "1.4.21"}
        ]
        mock_db.get_device_by_id.return_value = {
            "device_id": "laptop_1", "platform": "windows", "status": "trusted", "client_version": "1.4.21"
        }
        mock_db.get_setting.return_value = "chrome"

        ctx = {"db": mock_db, "relay_manager": mock_relay, "user_email": "test@example.com"}

        # 1. open_app
        res_app = await handle_open_app(1, {"name": "notepad", "target_device": "laptop_1"}, ctx)
        assert res_app["success"] is False
        assert res_app["status"] in ("unconfirmed", "failed")

        # 2. open_url
        res_url = await handle_open_url(1, {"url": "https://example.com", "target_device": "laptop_1"}, ctx)
        assert res_url["success"] is False
        assert res_url["status"] in ("unconfirmed", "failed")

        # 3. type_text
        res_type = await handle_type_text(1, {"text": "hello", "target_device": "laptop_1"}, ctx)
        assert res_type["success"] is False
        assert res_type["status"] in ("unconfirmed", "failed")

        # 4. press_keys
        res_keys = await handle_press_keys(1, {"keys": ["enter"], "target_device": "laptop_1"}, ctx)
        assert res_keys["success"] is False
        assert res_keys["status"] in ("unconfirmed", "failed")

        # 5. send_note
        res_note = await handle_send_note(1, {"title": "Note", "text": "Body", "target_device": "laptop_1"}, ctx)
        assert res_note["success"] is False
        assert res_note["status"] in ("unconfirmed", "failed")

        # 6. ring_phone
        res_ring = await handle_ring_phone(1, {"action": "start", "target_device": "laptop_1"}, ctx)
        assert res_ring["success"] is False
        assert res_ring["status"] in ("unconfirmed", "failed")


class TestC29StoreCatalogProtection:
    @pytest.mark.asyncio
    async def test_store_catalog_unavailable_blocks_generic_search(self):
        res = await execute_web_search(user_id=1, raw_query="what are the prices in our store today?")
        assert res.error == "STORE_CATALOG_UNAVAILABLE"
        assert "catalog" in res.context_text.lower()
        assert "could not find" in res.context_text.lower()


class TestC29RealDeviceCheckEndpoint:
    @pytest.mark.asyncio
    async def test_real_device_check_no_devices(self):
        app.dependency_overrides[get_current_user] = lambda: {"id": 1, "email": "test@example.com"}
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                with patch("app.main.db.get_user_devices", return_value=[]):
                    resp = await client.post("/api/devices/real-device-check", json={})
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["success"] is False
                    assert data["error"] == "NO_TRUSTED_DEVICES"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    @pytest.mark.asyncio
    async def test_real_device_check_executes_six_apps(self):
        app.dependency_overrides[get_current_user] = lambda: {"id": 1, "email": "test@example.com"}
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                mock_dev = {
                    "device_id": "test_laptop",
                    "name": "My Laptop",
                    "platform": "windows",
                    "status": "trusted",
                    "client_version": "1.4.21"
                }
                with patch("app.main.db.get_user_devices", return_value=[mock_dev]):
                    with patch("app.agent_tools.handle_open_app", new_callable=AsyncMock) as mock_handle:
                        async def side_effect(user_id, params, ctx):
                            app_name = params.get("name")
                            if app_name == "nonexistent_test_app_xyz":
                                return {"success": False, "status": "failed", "error": "NOT_FOUND"}
                            return {"success": True, "status": "succeeded", "message": f"{app_name} opened"}

                        mock_handle.side_effect = side_effect

                        resp = await client.post("/api/devices/real-device-check", json={})
                        assert resp.status_code == 200
                        data = resp.json()
                        assert data["success"] is True
                        assert len(data["devices"]) == 1
                        dev_res = data["devices"][0]
                        assert dev_res["device_id"] == "test_laptop"
                        assert len(dev_res["commands"]) == 6
                        apps_checked = [c["app"] for c in dev_res["commands"]]
                        assert "notepad" in apps_checked
                        assert "calculator" in apps_checked
                        assert "vscode" in apps_checked
                        assert "chrome" in apps_checked
                        assert "whatsapp" in apps_checked
                        assert "nonexistent_test_app_xyz" in apps_checked
        finally:
            app.dependency_overrides.pop(get_current_user, None)
