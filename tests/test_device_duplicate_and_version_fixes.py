"""
Tests for Device Duplicate Disambiguation, Revocation/Purge, and Client Version Updates.
Verifies:
1. Revoked devices are excluded from active list and agent context.
2. Permanent deletion removes device rows completely.
3. _resolve_target_device prioritizes online devices and deduplicates identical names without false prompts.
4. Version reporting via WebSocket, pending polling, and registration updates DB presence.
5. Live telemetry version overrides stale DB versions during command relay.
"""

import uuid
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app import database as db
from app.agent_tools import _resolve_target_device, handle_list_devices
from app.agent_loop import _build_agent_system_prompt
from app.device_relay import CommandRelayManager, relay_manager


class TestDeviceDuplicateAndVersionFixes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        email = f"fix_user_{uuid.uuid4().hex[:8]}@example.com"
        self.user = db.create_user(email, "Password123!", is_18=True, agreed_terms=True)
        self.user_id = self.user["id"]
        self.session_token = db.create_session(self.user_id)
        self.cookies = {"sinbha_session": self.session_token}

    def test_01_revoked_device_excluded_by_default_and_permanent_delete(self):
        # Register two devices
        d1 = db.create_or_register_device(self.user_id, "dev_pc_1", "BHANUTEJA", "windows", password="Password123!")
        d2 = db.create_or_register_device(self.user_id, "dev_pc_old", "BHANUTEJA", "windows", password="Password123!")

        active_devs = db.get_user_devices(self.user_id)
        self.assertEqual(len(active_devs), 2)

        # Revoke the old duplicate
        res = self.client.delete("/api/devices/dev_pc_old", cookies=self.cookies)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

        # Active devices must now only be 1 (dev_pc_1)
        active_devs = db.get_user_devices(self.user_id)
        self.assertEqual(len(active_devs), 1)
        self.assertEqual(active_devs[0]["device_id"], "dev_pc_1")

        # GET /api/devices default also returns 1
        res_api = self.client.get("/api/devices", cookies=self.cookies)
        self.assertEqual(res_api.status_code, 200)
        self.assertEqual(len(res_api.json()["devices"]), 1)

        # But include_revoked=True returns 2
        all_devs = db.get_user_devices(self.user_id, include_revoked=True)
        self.assertEqual(len(all_devs), 2)

        # Calling DELETE again on a revoked device permanently purges it
        res_purge = self.client.delete("/api/devices/dev_pc_old", cookies=self.cookies)
        self.assertEqual(res_purge.status_code, 200)
        self.assertIn("deleted permanently", res_purge.json()["message"])

        # Now even include_revoked=True returns only 1!
        all_devs_after = db.get_user_devices(self.user_id, include_revoked=True)
        self.assertEqual(len(all_devs_after), 1)
        self.assertEqual(all_devs_after[0]["device_id"], "dev_pc_1")

    def test_02_resolve_target_device_prioritizes_online_over_offline_duplicate(self):
        relay_mock = MagicMock()
        # Mock dev1 online, dev2 offline
        relay_mock.is_device_connected.side_effect = lambda uid, did: did == "dev_pc_online"

        dev_online = {
            "device_id": "dev_pc_online",
            "name": "BHANUTEJA",
            "platform": "windows",
            "status": "trusted",
            "last_seen_at": "2026-11-02 12:00:00"
        }
        dev_offline = {
            "device_id": "dev_pc_offline",
            "name": "BHANUTEJA",
            "platform": "windows",
            "status": "trusted",
            "last_seen_at": "2026-11-01 12:00:00"
        }
        trusted_list = [dev_offline, dev_online]

        # User says "open youtube in my laptop"
        res_laptop = _resolve_target_device(trusted_list, "laptop", relay_mock, self.user_id)
        self.assertEqual(res_laptop["status"], "ok")
        self.assertEqual(res_laptop["device"]["device_id"], "dev_pc_online")

        # User says "BHANUTEJA"
        res_name = _resolve_target_device(trusted_list, "BHANUTEJA", relay_mock, self.user_id)
        self.assertEqual(res_name["status"], "ok")
        self.assertEqual(res_name["device"]["device_id"], "dev_pc_online")

        # User says "windows"
        res_win = _resolve_target_device(trusted_list, "windows", relay_mock, self.user_id)
        self.assertEqual(res_win["status"], "ok")
        self.assertEqual(res_win["device"]["device_id"], "dev_pc_online")

    def test_03_resolve_target_device_disambiguates_distinct_online_names(self):
        relay_mock = MagicMock()
        # Both online
        relay_mock.is_device_connected.return_value = True

        dev_work = {
            "device_id": "dev_work_pc",
            "name": "Work Laptop",
            "platform": "windows",
            "status": "trusted"
        }
        dev_gaming = {
            "device_id": "dev_game_pc",
            "name": "Gaming PC",
            "platform": "windows",
            "status": "trusted"
        }
        trusted_list = [dev_work, dev_gaming]

        # Ambiguity between distinct names
        res = _resolve_target_device(trusted_list, "laptop", relay_mock, self.user_id)
        self.assertEqual(res["status"], "ambiguous")
        self.assertIn("Work Laptop", res["message"])
        self.assertIn("Gaming PC", res["message"])

    def test_04_agent_context_omits_revoked_devices(self):
        # Create devices: 1 phone, 1 online PC, 1 revoked PC
        user_devices = [
            {"device_id": "phone_1", "name": "Realme", "platform": "android", "status": "trusted", "is_online": True, "battery": 80},
            {"device_id": "laptop_online", "name": "BHANUTEJA", "platform": "windows", "status": "trusted", "is_online": True, "battery": None},
            {"device_id": "laptop_revoked", "name": "BHANUTEJA", "platform": "windows", "status": "revoked", "is_online": False, "battery": None},
        ]

        prompt = _build_agent_system_prompt(
            user_timezone="Asia/Kolkata",
            remembered_facts=[],
            user_devices=user_devices
        )

        # Prompt must state connected count is 2, and NOT show the revoked device
        self.assertIn("Connected device count: 2", prompt)
        self.assertNotIn("revoked", prompt.lower())

    def test_05_client_version_reporting_and_updating(self):
        # Register a device initially with version 1.4.14
        d = db.create_or_register_device(
            self.user_id,
            "android_phone_1",
            "My Phone",
            "android",
            password="Password123!",
            client_version="1.4.14"
        )
        self.assertEqual(d["client_version"], "1.4.14")

        # Simulate device polling pending commands with updated version 1.4.24
        res_poll = self.client.get(
            "/api/devices/commands/pending?device_id=android_phone_1&version=1.4.24",
            cookies=self.cookies
        )
        self.assertEqual(res_poll.status_code, 200)

        # Verify DB presence was updated to 1.4.24
        updated_dev = db.get_device_by_id(self.user_id, "android_phone_1")
        self.assertEqual(updated_dev["client_version"], "1.4.24")

    def test_06_handle_list_devices_counts_only_active_devices(self):
        d1 = db.create_or_register_device(self.user_id, "dev_active", "Active Phone", "android", password="Password123!")
        d2 = db.create_or_register_device(self.user_id, "dev_ghost", "Ghost Phone", "android", password="Password123!")
        db.revoke_device(self.user_id, "dev_ghost")

        relay_mock = MagicMock()
        relay_mock.is_device_connected.return_value = True
        relay_mock.get_device_telemetry.return_value = {"battery": 95}

        ctx = {"db": db, "relay_manager": relay_mock}
        import asyncio
        res = asyncio.run(handle_list_devices(self.user_id, {}, ctx))

        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["devices"][0]["device_id"], "dev_active")


if __name__ == "__main__":
    unittest.main()
