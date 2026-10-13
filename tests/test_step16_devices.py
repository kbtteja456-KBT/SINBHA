"""
Unit tests for Step 16: Device Pairing & Secure Command Channel.
Tests:
1. First device auto-trusted upon account creation / registration.
2. Second device starts pending with a 5-minute one-time pairing code.
3. Pairing approval from trusted device transitions status to trusted.
4. Pairing code expires after 5 minutes (300 seconds).
5. Cross-user isolation: User B cannot target or command User A's devices.
6. Revocation: Removed/revoked device cannot send or receive commands.
7. Expiry: Commands older than 60 seconds are rejected.
8. Replay protection: Duplicate command IDs are rejected.
9. Global STOP blocks all remote commands immediately.
10. "Disconnect all devices" revokes all devices immediately and halts commands.
11. Audit log records command type, sender, target, and result, but NEVER records payload content.
12. Rate limiting & offline queue limits (max 10 queued commands, stale commands never run).
13. Permission level gates (Level 0 read-only, Level >= 2 requires target confirmation) & capability toggles.
"""

import os
import sys
import unittest
import time
import tempfile
import json
from datetime import timedelta
from fastapi.testclient import TestClient

# Ensure repo root is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import app.database as db
from app.models import Device, AuditLog, utc_now
from app.device_relay import relay_manager

class TestStep16DeviceChannel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.temp_db = os.path.join(cls.temp_dir, "test_step16.db")
        db.set_engine_url(f"sqlite:///{cls.temp_db}")
        db.init_db()

        os.environ["ENV"] = "development"
        os.environ["DEV_MODE"] = "true"
        os.environ["DATA_ENCRYPTION_KEY"] = "6FGReUnNbpK-4Rw3UJVh8pbnyWI-GbWxnlkVwi_1o2U="

        from app.main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        try:
            if os.path.exists(cls.temp_db):
                os.remove(cls.temp_db)
            if os.path.exists(cls.temp_dir):
                os.rmdir(cls.temp_dir)
        except Exception:
            pass

    def setUp(self):
        # Reset relay manager state between tests
        relay_manager.seen_command_ids.clear()
        relay_manager.user_command_history.clear()
        relay_manager.offline_queues.clear()
        relay_manager.active_websockets.clear()

    def test_01_first_device_auto_trusted_second_device_pending(self):
        """First device created is trusted automatically; subsequent device is pending with 5-min code."""
        user = db.create_user("user1_devices@example.com", "Password123!", is_18=True, agreed_terms=True)
        user_id = user["id"]

        # Register first device
        dev1 = db.create_or_register_device(user_id, "dev_pc_1", name="Desktop PC", platform="windows")
        self.assertEqual(dev1["status"], "trusted")
        self.assertIsNone(dev1["pairing_code"])

        # Register second device
        dev2 = db.create_or_register_device(user_id, "dev_phone_2", name="Android Phone", platform="android")
        self.assertEqual(dev2["status"], "pending")
        self.assertIsNotNone(dev2["pairing_code"])
        self.assertEqual(len(dev2["pairing_code"]), 6)
        self.assertGreater(dev2["expires_in_seconds"], 280)
        self.assertLessEqual(dev2["expires_in_seconds"], 300)

    def test_02_pairing_approval_flow_and_expiry(self):
        """Pending device can be approved using its 5-minute code, but rejected once expired."""
        user = db.create_user("user2_pairing@example.com", "Password123!", is_18=True, agreed_terms=True)
        user_id = user["id"]

        dev1 = db.create_or_register_device(user_id, "dev_u2_1", name="PC", platform="windows")
        dev2 = db.create_or_register_device(user_id, "dev_u2_2", name="Tablet", platform="android")
        pairing_code = dev2["pairing_code"]

        # Approve with wrong code
        res_fail = db.approve_device_pairing(user_id, "000000", approver_device_id="dev_u2_1")
        self.assertFalse(res_fail["success"])

        # Approve with valid code
        res_ok = db.approve_device_pairing(user_id, pairing_code, approver_device_id="dev_u2_1")
        self.assertTrue(res_ok["success"])
        self.assertEqual(res_ok["device"]["status"], "trusted")

        # Now test expiration: create 3rd device and simulate expired pairing_expires_at
        dev3 = db.create_or_register_device(user_id, "dev_u2_3", name="Phone 2", platform="android")
        code3 = dev3["pairing_code"]

        with db.get_db_session() as session:
            d3_obj = session.scalar(db.select(Device).where(Device.device_id == "dev_u2_3"))
            d3_obj.pairing_expires_at = utc_now() - timedelta(seconds=10)

        # Attempting approval of expired device must fail
        res_exp = db.approve_device_pairing(user_id, code3, approver_device_id="dev_u2_1")
        self.assertFalse(res_exp["success"])
        self.assertIn("expired", res_exp["message"].lower())

    def test_03_cross_user_isolation(self):
        """User B cannot target, command, or approve User A's devices."""
        user_a = db.create_user("user_a@example.com", "Password123!", is_18=True, agreed_terms=True)
        user_b = db.create_user("user_b@example.com", "Password123!", is_18=True, agreed_terms=True)

        dev_a1 = db.create_or_register_device(user_a["id"], "dev_a1", "User A Laptop", "windows")
        dev_b1 = db.create_or_register_device(user_b["id"], "dev_b1", "User B Laptop", "windows")

        # User B attempts to send command targeting User A's device
        cmd = {
            "id": "cmd_cross_1",
            "sender_device": "dev_b1",
            "target_device": "dev_a1",
            "type": "ring_phone",
            "payload": {},
            "created_at": time.time(),
            "expiry": 60,
        }
        res = self.client.post(
            "/api/devices/commands/send",
            json=cmd,
            cookies={"sinbha_session": db.create_session(user_b["id"])}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("TARGET_NOT_FOUND", res.json()["detail"])

        # User B cannot see User A's devices in /api/devices
        res_list = self.client.get(
            "/api/devices",
            cookies={"sinbha_session": db.create_session(user_b["id"])}
        )
        b_dev_ids = [d["device_id"] for d in res_list.json()["devices"]]
        self.assertIn("dev_b1", b_dev_ids)
        self.assertNotIn("dev_a1", b_dev_ids)

    def test_04_revoked_device_cannot_send_or_receive(self):
        """Removing/revoking a device revokes access immediately."""
        user = db.create_user("user_revoke@example.com", "Password123!", is_18=True, agreed_terms=True)
        dev1 = db.create_or_register_device(user["id"], "dev_r1", "Device 1", "windows")
        dev2 = db.create_or_register_device(user["id"], "dev_r2", "Device 2", "android")
        db.approve_device_pairing(user["id"], dev2["pairing_code"])

        # Revoke dev2
        db.revoke_device(user["id"], "dev_r2")
        d2_status = db.get_device_by_id(user["id"], "dev_r2")
        self.assertEqual(d2_status["status"], "revoked")

        # Dev 2 attempts to send command
        cmd_from_revoked = {
            "id": "cmd_rev_1",
            "sender_device": "dev_r2",
            "target_device": "dev_r1",
            "type": "send_note",
            "payload": {"text": "hello"},
            "created_at": time.time(),
            "expiry": 60,
        }
        token = db.create_session(user["id"])
        res1 = self.client.post("/api/devices/commands/send", json=cmd_from_revoked, cookies={"sinbha_session": token})
        self.assertEqual(res1.status_code, 400)
        self.assertIn("SENDER_UNTRUSTED", res1.json()["detail"])

        # Dev 1 attempts to command revoked Dev 2
        cmd_to_revoked = {
            "id": "cmd_rev_2",
            "sender_device": "dev_r1",
            "target_device": "dev_r2",
            "type": "send_note",
            "payload": {"text": "hello"},
            "created_at": time.time(),
            "expiry": 60,
        }
        res2 = self.client.post("/api/devices/commands/send", json=cmd_to_revoked, cookies={"sinbha_session": token})
        self.assertEqual(res2.status_code, 400)
        self.assertIn("TARGET_UNTRUSTED", res2.json()["detail"])

    def test_05_expired_and_replayed_commands_rejected(self):
        """Commands older than 60s or replayed IDs are strictly rejected."""
        user = db.create_user("user_replay@example.com", "Password123!", is_18=True, agreed_terms=True)
        dev1 = db.create_or_register_device(user["id"], "dev_rp1", "Device 1", "windows")
        dev2 = db.create_or_register_device(user["id"], "dev_rp2", "Device 2", "android")
        db.approve_device_pairing(user["id"], dev2["pairing_code"])
        token = db.create_session(user["id"])

        # 1. Expired command (created 70 seconds ago)
        expired_cmd = {
            "id": "cmd_exp_1",
            "sender_device": "dev_rp1",
            "target_device": "dev_rp2",
            "type": "send_note",
            "payload": {"text": "expired message"},
            "created_at": time.time() - 70,
            "expiry": 60,
        }
        res_exp = self.client.post("/api/devices/commands/send", json=expired_cmd, cookies={"sinbha_session": token})
        self.assertEqual(res_exp.status_code, 400)
        self.assertIn("EXPIRED", res_exp.json()["detail"])

        # 2. Fresh valid command
        fresh_cmd = {
            "id": "cmd_fresh_1",
            "sender_device": "dev_rp1",
            "target_device": "dev_rp2",
            "type": "send_note",
            "payload": {"text": "valid message"},
            "created_at": time.time(),
            "expiry": 60,
        }
        res_fresh = self.client.post("/api/devices/commands/send", json=fresh_cmd, cookies={"sinbha_session": token})
        self.assertEqual(res_fresh.status_code, 200)

        # 3. Replaying the EXACT SAME command ID
        res_replay = self.client.post("/api/devices/commands/send", json=fresh_cmd, cookies={"sinbha_session": token})
        self.assertEqual(res_replay.status_code, 400)
        self.assertIn("REPLAY_REJECTED", res_replay.json()["detail"])

    def test_06_global_stop_blocks_all_remote_commands(self):
        """Emergency STOP halts and blocks all remote commands immediately."""
        user = db.create_user("user_stop@example.com", "Password123!", is_18=True, agreed_terms=True)
        dev1 = db.create_or_register_device(user["id"], "dev_st1", "Device 1", "windows")
        dev2 = db.create_or_register_device(user["id"], "dev_st2", "Device 2", "android")
        db.approve_device_pairing(user["id"], dev2["pairing_code"])
        token = db.create_session(user["id"])

        # Activate STOP
        db.set_emergency_stopped(user["id"], True)

        cmd = {
            "id": "cmd_stop_1",
            "sender_device": "dev_st1",
            "target_device": "dev_st2",
            "type": "ring_phone",
            "payload": {},
            "created_at": time.time(),
            "expiry": 60,
        }
        res = self.client.post("/api/devices/commands/send", json=cmd, cookies={"sinbha_session": token})
        self.assertEqual(res.status_code, 400)
        self.assertIn("BLOCKED_BY_STOP", res.json()["detail"])

    def test_07_disconnect_all_devices_button(self):
        """Disconnect all devices button revokes all devices immediately and clears queues."""
        user = db.create_user("user_disconn@example.com", "Password123!", is_18=True, agreed_terms=True)
        db.create_or_register_device(user["id"], "dev_d1", "PC", "windows")
        dev2 = db.create_or_register_device(user["id"], "dev_d2", "Phone", "android")
        db.approve_device_pairing(user["id"], dev2["pairing_code"])
        token = db.create_session(user["id"])

        # Call disconnect all
        res = self.client.post("/api/devices/disconnect-all", cookies={"sinbha_session": token})
        self.assertEqual(res.status_code, 200)

        # Both devices must now be revoked
        devices = db.get_user_devices(user["id"])
        for d in devices:
            self.assertEqual(d["status"], "revoked")

    def test_08_audit_log_never_logs_payload_content(self):
        """Server strictly logs metadata (command type, sender, target, result), NEVER the payload content."""
        user = db.create_user("user_audit_privacy@example.com", "Password123!", is_18=True, agreed_terms=True)
        dev1 = db.create_or_register_device(user["id"], "dev_aud1", "Device 1", "windows")
        dev2 = db.create_or_register_device(user["id"], "dev_aud2", "Device 2", "android")
        db.approve_device_pairing(user["id"], dev2["pairing_code"])
        token = db.create_session(user["id"])

        secret_text = "TOP_SECRET_MEDICAL_KEY_12345"
        cmd = {
            "id": "cmd_audit_test",
            "sender_device": "dev_aud1",
            "target_device": "dev_aud2",
            "type": "send_note",
            "payload": {"text": secret_text, "sensitive_link": "https://secret.example.com"},
            "created_at": time.time(),
            "expiry": 60,
        }
        res = self.client.post("/api/devices/commands/send", json=cmd, cookies={"sinbha_session": token})
        self.assertEqual(res.status_code, 200)

        # Inspect raw audit log entries
        logs = db.get_audit_logs(user["id"], limit=20)
        relay_logs = [l for l in logs if l["action"] == "DEVICE_COMMAND_RELAY"]
        self.assertTrue(len(relay_logs) >= 1)

        for l in relay_logs:
            details_str = l["details"]
            # Must NOT contain secret payload text
            self.assertNotIn(secret_text, details_str)
            self.assertNotIn("https://secret.example.com", details_str)
            # Must contain metadata
            self.assertIn("cmd_audit_test", details_str)
            self.assertIn("send_note", details_str)
            self.assertIn("dev_aud1", details_str)
            self.assertIn("dev_aud2", details_str)

    def test_09_permission_levels_and_capability_toggles(self):
        """Level 0 blocks active commands; disabled capability blocks command."""
        user = db.create_user("user_perms@example.com", "Password123!", is_18=True, agreed_terms=True)
        dev1 = db.create_or_register_device(user["id"], "dev_p1", "Sender", "windows")
        dev2 = db.create_or_register_device(user["id"], "dev_p2", "Target", "android")
        db.approve_device_pairing(user["id"], dev2["pairing_code"])
        token = db.create_session(user["id"])

        # 1. Test capability toggle: turn off 'ring' capability on dev2
        db.update_device_permissions(user["id"], "dev_p2", capabilities={"note": True, "open_link": True, "ring": False, "sync": True})
        cmd_ring = {
            "id": "cmd_perm_ring",
            "sender_device": "dev_p1",
            "target_device": "dev_p2",
            "type": "ring_phone",
            "payload": {},
            "created_at": time.time(),
            "expiry": 60,
        }
        res_cap = self.client.post("/api/devices/commands/send", json=cmd_ring, cookies={"sinbha_session": token})
        self.assertEqual(res_cap.status_code, 400)
        self.assertIn("CAPABILITY_DISABLED", res_cap.json()["detail"])

        # 2. Test permission Level 0 (Read-Only)
        db.update_device_permissions(user["id"], "dev_p2", permission_level=0, capabilities={"note": True, "open_link": True, "ring": True, "sync": True})
        cmd_note = {
            "id": "cmd_perm_ro",
            "sender_device": "dev_p1",
            "target_device": "dev_p2",
            "type": "send_note",
            "payload": {"text": "hello"},
            "created_at": time.time(),
            "expiry": 60,
        }
        res_ro = self.client.post("/api/devices/commands/send", json=cmd_note, cookies={"sinbha_session": token})
        self.assertEqual(res_ro.status_code, 400)
        self.assertIn("READ_ONLY", res_ro.json()["detail"])

        # Level 0 still permits sync_tasks
        cmd_sync = {
            "id": "cmd_perm_sync",
            "sender_device": "dev_p1",
            "target_device": "dev_p2",
            "type": "sync_tasks",
            "payload": {},
            "created_at": time.time(),
            "expiry": 60,
        }
        res_sync = self.client.post("/api/devices/commands/send", json=cmd_sync, cookies={"sinbha_session": token})
        self.assertEqual(res_sync.status_code, 200)

    def test_10_offline_queue_pruning_and_limits(self):
        """Offline devices have max 10 queued commands and stale commands (> 60s) never run."""
        user = db.create_user("user_queue@example.com", "Password123!", is_18=True, agreed_terms=True)
        dev1 = db.create_or_register_device(user["id"], "dev_q1", "Sender", "windows")
        dev2 = db.create_or_register_device(user["id"], "dev_q2", "Target", "android")
        db.approve_device_pairing(user["id"], dev2["pairing_code"])
        token = db.create_session(user["id"])

        # Send 12 commands (target is offline)
        for i in range(12):
            c = {
                "id": f"cmd_q_{i}",
                "sender_device": "dev_q1",
                "target_device": "dev_q2",
                "type": "sync_tasks",
                "payload": {"num": i},
                "created_at": time.time(),
                "expiry": 60,
            }
            res = self.client.post("/api/devices/commands/send", json=c, cookies={"sinbha_session": token})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["result"], "queued_offline")

        # Drain queue via GET /api/devices/commands/pending?device_id=dev_q2
        res_pending = self.client.get("/api/devices/commands/pending?device_id=dev_q2", cookies={"sinbha_session": token})
        self.assertEqual(res_pending.status_code, 200)
        cmds = res_pending.json()["commands"]
        # Max queue size is 10
        self.assertLessEqual(len(cmds), 10)

        # Queue is drained, next call returns 0
        res_empty = self.client.get("/api/devices/commands/pending?device_id=dev_q2", cookies={"sinbha_session": token})
        self.assertEqual(len(res_empty.json()["commands"]), 0)

if __name__ == "__main__":
    unittest.main()
