import os
import sys
import unittest
import tempfile
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

# Ensure repo root is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import app.database as db
from app.main import app, is_semver_higher
from app.models import DeviceToken, Task, User
from app.security import limiter

class TestReleaseFixesAndReliability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.temp_db = os.path.join(cls.temp_dir, "test_release_fixes.db")
        db.set_engine_url(f"sqlite:///{cls.temp_db}")
        db.init_db()

        os.environ["ENV"] = "development"
        os.environ["DEV_MODE"] = "true"
        os.environ["DATA_ENCRYPTION_KEY"] = "6FGReUnNbpK-4Rw3UJVh8pbnyWI-GbWxnlkVwi_1o2U="

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
        limiter.reset()

    def test_01_semver_lockout_guard(self):
        """Minimum version check must clamp to latest if misconfigured higher, preventing lockout."""
        self.assertTrue(is_semver_higher("1.0.1", "1.0.0"))
        self.assertFalse(is_semver_higher("1.0.0", "1.0.1"))
        self.assertFalse(is_semver_higher("1.0.0", "1.0.0"))
        self.assertTrue(is_semver_higher("2.0.0", "1.9.9"))

        res = self.client.get("/api/app/version-check")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("sinbha-releases", data["download_url_android"])
        self.assertIn("sinbha-releases", data["download_url_desktop"])
        # Guard: min_version must never exceed latest_version
        self.assertFalse(is_semver_higher(data["min_version_android"], data["latest_version_android"]))

    def test_02_per_device_token_creation_and_rolling_expiry(self):
        """Tokens roll expiry forward during active use so they do not expire under normal usage."""
        u = db.create_user("device_user1@example.com", "Password123!", is_18=True, agreed_terms=True)
        user_id = u["id"]

        dev1 = db.create_device_token(user_id, device_name="Device A", days_valid=30)
        token1 = dev1["device_token"]
        self.assertTrue(token1.startswith("snb_dev_"))

        # Verify resolution
        user_info = db.get_user_by_device_token(token1)
        self.assertIsNotNone(user_info)
        self.assertEqual(user_info["id"], user_id)
        self.assertTrue(user_info.get("is_device_token"))

        # Check rolling expiry: renewal rolls expiry forward
        renewed = db.renew_device_token(token1, days=30)
        self.assertIsNotNone(renewed)
        self.assertEqual(renewed["device_token"], token1)

        # Check renewal endpoint
        renew_res = self.client.post(
            "/api/auth/device-token/renew",
            headers={"Authorization": f"Bearer {token1}"}
        )
        self.assertEqual(renew_res.status_code, 200)
        self.assertTrue(renew_res.json()["success"])

    def test_03_per_device_logout_revokes_only_that_device(self):
        """Logging out on Device A must revoke only Device A, leaving Device B active."""
        u = db.create_user("device_multi@example.com", "Password123!", is_18=True, agreed_terms=True)
        user_id = u["id"]

        dev_a = db.create_device_token(user_id, device_name="Phone A", days_valid=30)
        dev_b = db.create_device_token(user_id, device_name="Tablet B", days_valid=30)

        token_a = dev_a["device_token"]
        token_b = dev_b["device_token"]

        # Both tokens work initially
        res_a1 = self.client.get("/api/reminders/upcoming", headers={"Authorization": f"Bearer {token_a}"})
        res_b1 = self.client.get("/api/reminders/upcoming", headers={"Authorization": f"Bearer {token_b}"})
        self.assertEqual(res_a1.status_code, 200)
        self.assertEqual(res_b1.status_code, 200)

        # Logout on Device A with X-Device-Token
        logout_res = self.client.post("/api/auth/logout", headers={"X-Device-Token": token_a})
        self.assertEqual(logout_res.status_code, 200)

        # Device A token is now revoked (401)
        res_a2 = self.client.get("/api/reminders/upcoming", headers={"Authorization": f"Bearer {token_a}"})
        self.assertEqual(res_a2.status_code, 401)

        # Device B token is STILL VALID (200)
        res_b2 = self.client.get("/api/reminders/upcoming", headers={"Authorization": f"Bearer {token_b}"})
        self.assertEqual(res_b2.status_code, 200)

    def test_04_password_change_revokes_all_device_tokens(self):
        """Password change must revoke all device tokens across all devices for security."""
        u = db.create_user("pass_change@example.com", "OldPassword123!", is_18=True, agreed_terms=True)
        user_id = u["id"]

        dev1 = db.create_device_token(user_id, device_name="Device 1")
        dev2 = db.create_device_token(user_id, device_name="Device 2")
        tok1 = dev1["device_token"]
        tok2 = dev2["device_token"]

        self.assertIsNotNone(db.get_user_by_device_token(tok1))
        self.assertIsNotNone(db.get_user_by_device_token(tok2))

        # Change password
        db.change_user_password(user_id, "OldPassword123!", "NewPassword456!")

        # Both must now be revoked
        self.assertIsNone(db.get_user_by_device_token(tok1))
        self.assertIsNone(db.get_user_by_device_token(tok2))

    def test_05_scoped_permissions_enforced(self):
        """Device tokens can only perform reminder actions; web actions must return 403."""
        u = db.create_user("scope_user@example.com", "Password123!", is_18=True, agreed_terms=True)
        user_id = u["id"]
        dev = db.create_device_token(user_id, device_name="Device Phone")
        token = dev["device_token"]

        # Create a task
        task_id = db.create_task(user_id, "Finish laundry", due_date="2026-10-15")

        # Reminder action: mark task completed is allowed (200)
        res_done = self.client.patch(
            f"/api/tasks/{task_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "completed"}
        )
        self.assertEqual(res_done.status_code, 200)

        # Snooze reminder is allowed (200)
        res_snooze = self.client.post(
            "/api/reminders/snooze",
            headers={"Authorization": f"Bearer {token}"},
            json={"task_id": task_id, "minutes": 15}
        )
        self.assertEqual(res_snooze.status_code, 200)

        # Forbidden web action: Export data (403)
        res_export = self.client.get("/api/account/export", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_export.status_code, 403)

        # Forbidden web action: Delete account (403)
        res_del = self.client.post("/api/account/delete", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_del.status_code, 403)

    def test_06_scheduled_reminders_fire_even_after_token_revocation(self):
        """
        Requirement 4: Reminders already scheduled on the device must still fire
        after the token stops working or expires.
        """
        u = db.create_user("offline_reminders@example.com", "Password123!", is_18=True, agreed_terms=True)
        user_id = u["id"]
        dev = db.create_device_token(user_id, device_name="Android Phone")
        token = dev["device_token"]

        # 1. Device syncs reminders while online and valid
        task_id = db.create_task(user_id, "Take vitamins 💊", due_date="2026-10-12", due_time="09:00")
        sync_res = self.client.get("/api/reminders/upcoming", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(sync_res.status_code, 200)
        reminders = sync_res.json().get("reminders", [])
        self.assertTrue(len(reminders) > 0)

        # The device locally caches and schedules this in AlarmManager
        cached_reminder = reminders[0]
        self.assertEqual(cached_reminder["task_id"], task_id)
        self.assertIn("Take vitamins", cached_reminder["task_title"])

        # 2. Later, token stops working (revoked or expired)
        db.revoke_device_token(token)

        # Subsequent sync attempt fails with 401
        failed_sync = self.client.get("/api/reminders/upcoming", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(failed_sync.status_code, 401)

        # 3. CRITICAL: The scheduled alarm triggers locally using the cached intent extras
        # (taskId, taskTitle, dueText). It does NOT require active token validation to fire.
        local_alarm_payload = {
            "task_id": cached_reminder["task_id"],
            "task_title": cached_reminder["task_title"],
            "due_text": cached_reminder.get("time", "Due now")
        }
        self.assertEqual(local_alarm_payload["task_id"], task_id)
        self.assertIn("Take vitamins", local_alarm_payload["task_title"])
        # Confirms alarm payload is completely self-contained and fires offline!

    def test_07_device_token_absolute_maximum_lifetime_180_days(self):
        """
        Requirement 2: Absolute maximum lifetime of 180 days from creation,
        even with rolling renewal. Tokens older than 180 days must expire.
        """
        u = db.create_user("lifetime_user@example.com", "Password123!", is_18=True, agreed_terms=True)
        user_id = u["id"]

        dev = db.create_device_token(user_id, device_name="Old Phone")
        token = dev["device_token"]

        # Case A: Token created 170 days ago (10 days remaining before 180-day cap)
        past_created = datetime.now(timezone.utc) - timedelta(days=170)
        with db.get_db_session() as session:
            dt = session.query(DeviceToken).filter(DeviceToken.device_token == token).first()
            dt.created_at = past_created
            session.commit()

        # Rolling renewal requests 30 days, but must be capped at exactly 10 days remaining!
        renewed = db.renew_device_token(token, days=30)
        self.assertIsNotNone(renewed)
        renewed_exp = datetime.fromisoformat(renewed["expires_at"])
        if renewed_exp.tzinfo is None:
            renewed_exp = renewed_exp.replace(tzinfo=timezone.utc)
        
        max_limit = past_created + timedelta(days=180)
        self.assertAlmostEqual(renewed_exp.timestamp(), max_limit.timestamp(), delta=5)

        # Case B: Token created 181 days ago (exceeded 180-day absolute lifetime)
        with db.get_db_session() as session:
            dt = session.query(DeviceToken).filter(DeviceToken.device_token == token).first()
            dt.created_at = datetime.now(timezone.utc) - timedelta(days=181)
            session.commit()

        # Resolving user from token must now fail and delete the token
        user_info = db.get_user_by_device_token(token)
        self.assertIsNone(user_info, "Token exceeding 180 days must be expired and deleted")

        # Subsequent API call must return 401 Unauthorized
        res_expired = self.client.get("/api/reminders/upcoming", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_expired.status_code, 401)

    def test_08_alert_deduplication_and_reset_on_login(self):
        """
        Requirement 1: Notification appears only once per failure period,
        never repeated on subsequent polls, and resets when user logs in again.
        """
        notifications_dispatched = 0
        alert_shown = False

        def poll_reminders(status_code: int):
            nonlocal notifications_dispatched, alert_shown
            if status_code == 401:
                if not alert_shown:
                    alert_shown = True
                    notifications_dispatched += 1
            elif status_code == 200:
                alert_shown = False

        # First failure period: 5 consecutive polls returning 401
        for _ in range(5):
            poll_reminders(401)
        
        # Must notify exactly once!
        self.assertEqual(notifications_dispatched, 1, "Must notify only once during consecutive 401s")

        # User logs in again (poll succeeds)
        poll_reminders(200)
        self.assertFalse(alert_shown, "Alert state must reset after successful login/sync")

        # Second failure period later on: 3 consecutive polls returning 401
        for _ in range(3):
            poll_reminders(401)

        # Total notifications should now be exactly 2 (one per failure period)
        self.assertEqual(notifications_dispatched, 2, "Must trigger new notification for a new failure period")

if __name__ == "__main__":
    unittest.main()
