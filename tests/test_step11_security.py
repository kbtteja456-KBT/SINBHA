import os
import sys
import unittest
from unittest import mock
import time
import tempfile
import sqlite3
from fastapi.testclient import TestClient

# Ensure repo root is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import app.database as db
from app.crypto import encrypt_text, decrypt_text
from app.models import Message, Fact, User
from app.security import validate_production_config, limiter

class TestStep11SecurityHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.temp_db = os.path.join(cls.temp_dir, "test_step11.db")
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
        # Reset in-memory rate limiter before each test so tests don't interfere
        limiter.reset()

    def test_01_encryption_at_rest_for_messages_and_facts(self):
        """Messages and facts must be stored encrypted with enc:: prefix and never in plaintext."""
        u = db.create_user("crypto_user@example.com", "StrongPassword123!", is_18=True, agreed_terms=True)
        user_id = u["id"]

        secret_msg = "My sensitive secret is 9988-1122"
        db.save_message(user_id, "user", secret_msg)

        secret_fact = "User secret medical detail: allergic to penicillin"
        db.add_fact(user_id, secret_fact, "medical")

        # Inspect raw SQLite rows directly
        conn = sqlite3.connect(self.temp_db)
        cur = conn.cursor()

        cur.execute("SELECT content FROM messages WHERE user_id = ?", (user_id,))
        raw_msg_row = cur.fetchone()[0]
        self.assertNotIn(secret_msg, raw_msg_row, "Raw database row MUST NOT contain plaintext chat message!")
        self.assertTrue(raw_msg_row.startswith("enc::"), "Encrypted message must have enc:: prefix!")

        cur.execute("SELECT fact FROM facts WHERE user_id = ?", (user_id,))
        raw_fact_row = cur.fetchone()[0]
        self.assertNotIn(secret_fact, raw_fact_row, "Raw database row MUST NOT contain plaintext fact!")
        self.assertTrue(raw_fact_row.startswith("enc::"), "Encrypted fact must have enc:: prefix!")
        conn.close()

        # Database helpers decrypt transparently
        messages = db.get_all_messages(user_id)
        self.assertEqual(messages[0]["content"], secret_msg)

        facts = db.get_all_facts(user_id)
        self.assertEqual(facts[0]["fact"], secret_fact)

    def test_02_csrf_protection_blocks_malicious_origin(self):
        """State-changing requests from untrusted origins or without AJAX header must receive 403."""
        u = db.create_user("csrf_user@example.com", "StrongPassword123!", is_18=True, agreed_terms=True)
        token = db.create_session(u["id"])

        # Cross-site attack simulation: Malicious Origin header without custom header
        res_blocked = self.client.post(
            "/api/settings",
            json={"persistence": "persistent"},
            headers={
                "Origin": "https://evil-attacker.com",
                "Cookie": f"sinbha_session={token}"
            }
        )
        self.assertEqual(res_blocked.status_code, 403)
        self.assertIn("CSRF", res_blocked.json()["detail"])

        # Legitimate request with X-Requested-With header passes CSRF verification
        res_ok = self.client.post(
            "/api/settings",
            json={"persistence": "persistent"},
            headers={
                "Cookie": f"sinbha_session={token}",
                "X-Requested-With": "XMLHttpRequest"
            }
        )
        self.assertEqual(res_ok.status_code, 200)

    def test_03_security_headers_present(self):
        """Security headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options) must be present."""
        res = self.client.get("/api/info")
        self.assertEqual(res.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(res.headers.get("x-frame-options"), "DENY")
        self.assertIn("content-security-policy", res.headers)
        self.assertIn("default-src 'self'", res.headers["content-security-policy"])

    def test_04_xss_protection_preserves_plain_text(self):
        """Payloads like <img src=x onerror=alert(1)> must be stored as plain text, never raw HTML."""
        u = db.create_user("xss_user@example.com", "StrongPassword123!", is_18=True, agreed_terms=True)
        token = db.create_session(u["id"])
        headers = {"Cookie": f"sinbha_session={token}", "X-Requested-With": "XMLHttpRequest"}

        xss_payload = '<img src=x onerror=alert(1)>'
        db.save_message(u["id"], "user", xss_payload)
        db.create_task(u["id"], xss_payload)
        db.add_fact(u["id"], xss_payload, "general")

        # Retrieve via API endpoints
        res_msgs = self.client.get("/api/messages", headers=headers)
        self.assertEqual(res_msgs.status_code, 200)
        msgs = res_msgs.json()["messages"]
        self.assertTrue(any(m["content"] == xss_payload for m in msgs))

        res_tasks = self.client.get("/api/tasks", headers=headers)
        self.assertEqual(res_tasks.status_code, 200)
        tasks = res_tasks.json()["tasks"]
        self.assertTrue(any(t["title"] == xss_payload for t in tasks))

    def test_05_input_limits_message_length(self):
        """Chat messages exceeding 2,000 characters must be rejected with 400 Bad Request."""
        u = db.create_user("len_user@example.com", "StrongPassword123!", is_18=True, agreed_terms=True)
        token = db.create_session(u["id"])
        headers = {"Cookie": f"sinbha_session={token}", "X-Requested-With": "XMLHttpRequest"}

        huge_message = "A" * 2005
        res = self.client.post("/api/chat", json={"message": huge_message}, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn("under 2,000 characters", res.json()["detail"])

    def test_06_password_change_invalidates_all_previous_sessions(self):
        """Changing account password must immediately invalidate existing active sessions."""
        email = f"pwd_user_{int(time.time())}@example.com"
        u = db.create_user(email, "InitialPassword123!", is_18=True, agreed_terms=True)
        old_token = db.create_session(u["id"])
        headers_old = {"Cookie": f"sinbha_session={old_token}", "X-Requested-With": "XMLHttpRequest"}

        # Verify old session works
        res_msgs = self.client.get("/api/messages", headers=headers_old)
        self.assertEqual(res_msgs.status_code, 200)

        # Change password
        res_chg = self.client.post("/api/account/change-password", json={
            "old_password": "InitialPassword123!",
            "new_password": "UpdatedPassword456!"
        }, headers=headers_old)
        self.assertEqual(res_chg.status_code, 200)

        # Old session must now be rejected (401) on protected endpoints
        res_msgs_after = self.client.get("/api/messages", headers=headers_old)
        self.assertEqual(res_msgs_after.status_code, 401)

        # /api/auth/me should indicate logged_in: False
        res_me = self.client.get("/api/auth/me", headers=headers_old)
        self.assertEqual(res_me.status_code, 200)
        self.assertFalse(res_me.json()["logged_in"])

        # Login with new password succeeds
        res_login_new = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "UpdatedPassword456!"
        }, headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(res_login_new.status_code, 200)

    def test_07_data_rights_export_and_account_deletion(self):
        """User can export all their data as JSON and delete their account completely."""
        email = f"rights_user_{int(time.time())}@example.com"
        u = db.create_user(email, "StrongPassword123!", is_18=True, agreed_terms=True)
        user_id = u["id"]
        token = db.create_session(user_id)
        headers = {"Cookie": f"sinbha_session={token}", "X-Requested-With": "XMLHttpRequest"}

        # Add data
        db.save_message(user_id, "user", "My exportable message")
        db.add_fact(user_id, "Loves midnight snacks", "preference")
        db.create_task(user_id, "Exportable task")

        # Test Export
        res_export = self.client.get("/api/account/export", headers=headers)
        self.assertEqual(res_export.status_code, 200)
        data = res_export.json()
        self.assertEqual(data["user"]["email"], email)
        self.assertTrue(any(m["content"] == "My exportable message" for m in data["messages"]))
        self.assertTrue(any(f["fact"] == "Loves midnight snacks" for f in data["facts"]))
        self.assertTrue(any(t["title"] == "Exportable task" for t in data["tasks"]))

        # Test Account Deletion
        res_del = self.client.delete("/api/account", headers=headers)
        self.assertEqual(res_del.status_code, 200)

        # After deletion, data must be gone and session invalid
        self.assertEqual(len(db.get_all_messages(user_id)), 0)
        self.assertEqual(len(db.get_all_facts(user_id)), 0)
        self.assertEqual(len(db.get_all_tasks(user_id)), 0)
        res_msg_del = self.client.get("/api/messages", headers=headers)
        self.assertEqual(res_msg_del.status_code, 401)

    def test_08_admin_cannot_read_other_users_chat_messages(self):
        """Admins must never be able to inspect another user's chat messages or memory."""
        # Admin user
        admin = db.create_user("admin_sec@example.com", "AdminPassword123!", is_18=True, agreed_terms=True)
        admin_token = db.create_session(admin["id"])
        admin_headers = {"Cookie": f"sinbha_session={admin_token}", "X-Requested-With": "XMLHttpRequest"}

        # Normal user
        victim = db.create_user("victim_sec@example.com", "VictimPassword123!", is_18=True, agreed_terms=True)
        victim_id = victim["id"]
        db.save_message(victim_id, "user", "Victim's highly confidential conversation")

        # Admin calls /api/messages -> gets only admin's messages, never victim's
        admin_msgs_res = self.client.get("/api/messages", headers=admin_headers)
        self.assertEqual(admin_msgs_res.status_code, 200)
        admin_msgs = admin_msgs_res.json()["messages"]
        self.assertFalse(any("confidential" in m["content"] for m in admin_msgs))

    def test_09_production_mode_refusal_when_secrets_missing(self):
        """Refuses to start in production if DATA_ENCRYPTION_KEY or proper DB is missing."""
        old_env = os.environ.get("ENV")
        old_key = os.environ.get("DATA_ENCRYPTION_KEY")
        try:
            os.environ["ENV"] = "production"
            os.environ.pop("DATA_ENCRYPTION_KEY", None)
            with self.assertRaises(RuntimeError) as ctx:
                validate_production_config()
            self.assertIn("DATA_ENCRYPTION_KEY", str(ctx.exception))
        finally:
            if old_env:
                os.environ["ENV"] = old_env
            else:
                os.environ.pop("ENV", None)
            if old_key:
                os.environ["DATA_ENCRYPTION_KEY"] = old_key

    def test_10_sql_injection_defense(self):
        """ORM parameter binding prevents SQL injection in all user inputs."""
        u = db.create_user("sqli_user@example.com", "StrongPassword123!", is_18=True, agreed_terms=True)
        user_id = u["id"]

        sql_injection_payload = "'; DROP TABLE messages; --"
        db.save_message(user_id, "user", sql_injection_payload)
        db.create_task(user_id, sql_injection_payload)
        db.add_fact(user_id, sql_injection_payload, "sql_test")

        # Confirm the tables still exist and query safely
        msgs = db.get_all_messages(user_id)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["content"], sql_injection_payload)

        tasks = db.get_all_tasks(user_id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], sql_injection_payload)

    @mock.patch("app.main.extract_explicit_facts", new_callable=mock.AsyncMock)
    @mock.patch("app.main.call_sinbha_brain")
    @mock.patch("app.agent_loop.run_agent_loop", new_callable=mock.AsyncMock)
    def test_11_rate_limit_trips_429(self, mock_loop, mock_brain, mock_facts):
        """Rapid chat requests trip rate limiting with friendly 429 response."""
        mock_facts.return_value = []
        mock_brain.return_value = {"reply": "Fast mock response 🌸", "status": "ok"}
        from app.agent_loop import AgentResult
        mock_loop.return_value = AgentResult(reply="Fast mock response 🌸")
        u = db.create_user("ratelimit_user@example.com", "StrongPassword123!", is_18=True, agreed_terms=True)
        token = db.create_session(u["id"])
        headers = {"Cookie": f"sinbha_session={token}", "X-Requested-With": "XMLHttpRequest"}

        # Simulate 26 rapid requests to /api/chat (limit is 25 per minute)
        status_codes = []
        for _ in range(27):
            res = self.client.post("/api/chat", json={"message": "Hello"}, headers=headers)
            status_codes.append(res.status_code)

        self.assertIn(429, status_codes)
        res_429 = self.client.post("/api/chat", json={"message": "Hello"}, headers=headers)
        self.assertEqual(res_429.status_code, 429)
        self.assertIn("Whoa, you're typing really fast", res_429.json()["detail"])

if __name__ == "__main__":
    unittest.main()
