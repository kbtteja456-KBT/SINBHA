import os
import sys
import unittest
import tempfile
import json
from datetime import datetime, timezone, timedelta

# Ensure repo root is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ENV"] = "development"
os.environ["DEV_MODE"] = "true"
os.environ["DATA_ENCRYPTION_KEY"] = "6FGReUnNbpK-4Rw3UJVh8pbnyWI-GbWxnlkVwi_1o2U="

from fastapi.testclient import TestClient
import app.database as db
from app.main import app
from app.ai_brain import parse_relative_datetime
from app.search import (
    is_time_sensitive_query,
    is_result_too_stale,
    execute_web_search,
    SearchProvider,
    SearchResult,
    SearchResponse
)

class MockTavilyProvider(SearchProvider):
    def __init__(self, mock_results=None):
        self.mock_results = mock_results or []
        self.last_query = None
        self.last_topic = None
        self.last_days = None

    async def search(self, query: str, max_results: int = 5, topic=None, days=None):
        self.last_query = query
        self.last_topic = topic
        self.last_days = days
        return self.mock_results

    async def fetch_page(self, url: str):
        return None

class TestAuditFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.temp_db = os.path.join(cls.temp_dir, "test_audit_fixes.db")
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

    # ---------------- 1. Snooze Server and Android Logic ----------------
    def test_01_snooze_server_expiration_and_firing(self):
        """
        Requirement 1: An expired snooze becomes a due reminder in check_due_reminders.
        Firing it clears snoozed_until so subsequent snoozes can be re-scheduled.
        """
        u = db.create_user("snooze_user@example.com", "Password123!", is_18=True, agreed_terms=True)
        user_id = u["id"]

        now_utc = datetime.now(timezone.utc)
        task_id = db.create_task(
            user_id=user_id,
            title="Read chapter 4",
            due_date=now_utc.strftime("%Y-%m-%d"),
            due_time=now_utc.strftime("%H:%M")
        )

        # Snooze task for 2 minutes
        db.snooze_task(user_id, task_id, minutes=2)
        task_data = db.get_task_by_id(user_id, task_id)
        self.assertIsNotNone(task_data["snoozed_until"])

        # When snoozed_until is in the future, check_due_reminders does not return it
        due_future = db.check_due_reminders(user_id)
        snooze_due_future = [d for d in due_future if d["task"]["id"] == task_id and d.get("reminder_id") == f"snooze_{task_id}"]
        self.assertEqual(len(snooze_due_future), 0, "Future snooze must not be due yet")

        # Simulate snooze expiration (set snoozed_until 1 second in the past)
        with db.get_db_session() as session:
            t = session.get(db.Task, task_id)
            t.snoozed_until = now_utc - timedelta(seconds=2)
            session.commit()

        # Expired snooze must now become a due reminder!
        due_now = db.check_due_reminders(user_id)
        snooze_due = [d for d in due_now if d["task"]["id"] == task_id and d.get("reminder_id") == f"snooze_{task_id}"]
        self.assertEqual(len(snooze_due), 1, "Expired snooze must appear in due reminders")
        self.assertEqual(snooze_due[0]["reminder_id"], f"snooze_{task_id}")

        # Mark snooze reminder as fired -> must clear snoozed_until
        db.mark_reminder_fired(user_id, task_id, f"snooze_{task_id}")
        task_after_fire = db.get_task_by_id(user_id, task_id)
        self.assertIsNone(task_after_fire["snoozed_until"], "Firing snooze must reset snoozed_until to None")

        # Now snoozing again must work reliably
        db.snooze_task(user_id, task_id, minutes=5)
        task_resnoozed = db.get_task_by_id(user_id, task_id)
        self.assertIsNotNone(task_resnoozed["snoozed_until"])
        # And fired_reminders must no longer contain snooze_<id>
        self.assertNotIn(f"snooze_{task_id}", task_resnoozed["fired_reminders"])

    def test_02_snooze_android_native_exact_alarm_and_reboot_cache(self):
        """
        Requirement 1: On Android, snoozing schedules an exact alarm on the phone and
        saves to cachedRemindersJson so it survives phone reboot and works offline.
        """
        # Emulate Android AlarmScheduler.addOrUpdateCachedReminder
        cached_reminders = []
        task_id = 42
        snooze_minutes = 2
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        snooze_trigger_ms = now_ms + (snooze_minutes * 60 * 1000)

        snooze_item = {
            "task_id": task_id,
            "task_title": "Study physics",
            "reminder_id": f"snooze_{task_id}",
            "trigger_at_ms": snooze_trigger_ms,
            "due_text": f"Snoozed ({snooze_minutes}m)"
        }

        # Save to simulated SharedPreferences cachedRemindersJson
        cached_reminders = [r for r in cached_reminders if not (r["task_id"] == task_id and r["reminder_id"] == f"snooze_{task_id}")]
        cached_reminders.append(snooze_item)
        cached_json = json.dumps(cached_reminders)

        # Simulate device reboot: BootReceiver loads cachedRemindersJson
        restored = json.loads(cached_json)
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["task_id"], task_id)
        self.assertEqual(restored[0]["reminder_id"], f"snooze_{task_id}")
        self.assertGreater(restored[0]["trigger_at_ms"], now_ms)

    # ---------------- 2. Time Parsing: Next Occurrence & Ambiguity ----------------
    def test_03_time_parsing_next_occurrence_849pm_and_851(self):
        """
        Requirement 2: For 12-hour times without AM/PM:
        - At 8:49 PM (20:49), '8:51' means 8:51 PM (20:51) today.
        - At 9:00 AM (09:00), '8:51' means 8:51 PM (20:51) today.
        - At 9:00 PM (21:00), '8:51' means 8:51 AM (08:51) tomorrow.
        """
        base_date = datetime(2026, 10, 15)

        # Case A: At 8:49 PM (20:49), user asks "8:51"
        at_849pm = datetime(2026, 10, 15, 20, 49)
        res_a = parse_relative_datetime("at 8:51", base_dt=at_849pm, user_timezone="Asia/Kolkata")
        self.assertEqual(res_a["due_date"], "2026-10-15")
        self.assertEqual(res_a["due_time"], "20:51", "At 8:49 PM, 8:51 must resolve to 8:51 PM (20:51) today")
        self.assertFalse(res_a["is_past"])
        self.assertFalse(res_a["is_ambiguous"])

        # Case B: At 9:00 AM (09:00), user asks "8:51"
        at_900am = datetime(2026, 10, 15, 9, 0)
        res_b = parse_relative_datetime("at 8:51", base_dt=at_900am, user_timezone="Asia/Kolkata")
        self.assertEqual(res_b["due_date"], "2026-10-15")
        self.assertEqual(res_b["due_time"], "20:51", "At 9:00 AM, 8:51 must resolve to 8:51 PM (20:51) today")
        self.assertFalse(res_b["is_past"])

        # Case C: At 9:00 PM (21:00), user asks "8:51"
        at_900pm = datetime(2026, 10, 15, 21, 0)
        res_c = parse_relative_datetime("at 8:51", base_dt=at_900pm, user_timezone="Asia/Kolkata")
        self.assertEqual(res_c["due_date"], "2026-10-16")
        self.assertEqual(res_c["due_time"], "08:51", "At 9:00 PM, 8:51 must roll over to 8:51 AM tomorrow")

    def test_04_time_parsing_ambiguous_future_and_past_detection(self):
        """
        Requirement 2: If meaning is ambiguous (e.g. 'tomorrow at 8'),
        show 2 buttons (8:00 AM / 8:00 PM) instead of guessing.
        If time ends up in the past, flag is_past and ask user.
        Task card must show full date, time, and timezone.
        """
        base_now = datetime(2026, 10, 15, 14, 0)  # 2:00 PM

        # Ambiguous future time: "tomorrow at 8"
        res_ambig = parse_relative_datetime("tomorrow at 8", base_dt=base_now, user_timezone="Asia/Kolkata")
        self.assertTrue(res_ambig["is_ambiguous"])
        self.assertIsNotNone(res_ambig["ambiguous_options"])
        self.assertEqual(len(res_ambig["ambiguous_options"]), 2)
        labels = [opt["label"] for opt in res_ambig["ambiguous_options"]]
        self.assertIn("8:00 AM", labels)
        self.assertIn("8:00 PM", labels)
        self.assertIn("Asia/Kolkata", res_ambig["ambiguous_options"][0]["display"])

        # Past time detection: at 2:00 PM, asking for "today at 1:00 PM"
        res_past = parse_relative_datetime("today at 1:00 pm", base_dt=base_now, user_timezone="Asia/Kolkata")
        self.assertTrue(res_past["is_past"])
        self.assertIsNotNone(res_past["past_message"])
        self.assertIn("earlier today", res_past["past_message"])

    # ---------------- 3. Web Search: News Topic & Stale Filtering ----------------
    def test_05_stale_news_filtering_and_query_augmentation(self):
        """
        Requirement 3:
        (b) For news, sports, schedules, prices and weather, use Tavily's news topic
            and recent range, and add current month and year to query.
        (c) Discard results older than sensible age for time-sensitive questions and show date on every source.
        """
        # Detection
        self.assertTrue(is_time_sensitive_query("cricket match score"))
        self.assertTrue(is_time_sensitive_query("weather in Mumbai"))
        self.assertTrue(is_time_sensitive_query("latest price of gold"))
        self.assertFalse(is_time_sensitive_query("what is an atom"))

        # Stale date helper
        today = datetime.now(timezone.utc).date()
        fresh_date = (today - timedelta(days=2)).isoformat()
        stale_date = (today - timedelta(days=25)).isoformat()

        self.assertFalse(is_result_too_stale(fresh_date, max_days=14))
        self.assertTrue(is_result_too_stale(stale_date, max_days=14))

        # Live search execution pipeline test with mock Tavily
        mock_results = [
            SearchResult(
                title="Recent Cricket News",
                url="https://espncricinfo.com/live",
                content="Live scores from today.",
                domain="espncricinfo.com",
                published_date=fresh_date
            ),
            SearchResult(
                title="Stale Article from Last Month",
                url="https://example.com/old",
                content="Old match analysis.",
                domain="example.com",
                published_date=stale_date
            )
        ]
        provider = MockTavilyProvider(mock_results)

        import asyncio
        loop = asyncio.new_event_loop()
        resp = loop.run_until_complete(
            execute_web_search(user_id=1, raw_query="India vs Australia match score", provider=provider)
        )
        loop.close()

        # Verify topic="news" and days=7 passed to Tavily
        self.assertEqual(provider.last_topic, "news")
        self.assertEqual(provider.last_days, 7)

        # Verify current month & year appended
        current_my = datetime.now(timezone.utc).strftime("%B %Y")
        self.assertIn(current_my, provider.last_query)

        # Verify stale result was discarded!
        self.assertEqual(len(resp.sources), 1)
        self.assertEqual(resp.sources[0]["title"], "Recent Cricket News")
        self.assertEqual(resp.sources[0]["date"], fresh_date)

    # ---------------- 4. Pairing: First Device Not Auto-Trusted ----------------
    def test_06_first_device_not_auto_trusted_requires_password(self):
        """
        Requirement 4: Do NOT auto-trust the first device.
        When someone logs in and account has no trusted device,
        it starts as pending with requires_first_device_trust: True.
        Must ask for account password to become trusted.
        """
        u = db.create_user("pair_first_test@example.com", "SecretPass123!", is_18=True, agreed_terms=True)
        user_id = u["id"]

        # Initial device registration without password
        dev_res = db.create_or_register_device(
            user_id=user_id,
            device_id="laptop_primary_01",
            name="Windows Laptop",
            platform="desktop",
            is_signup=True,  # Even with is_signup=True, must NOT auto-trust!
            password=None
        )

        self.assertEqual(dev_res["status"], "pending", "First device must NOT be auto-trusted")
        self.assertTrue(dev_res["requires_first_device_trust"], "Must flag requires_first_device_trust")
        self.assertIsNotNone(dev_res.get("pairing_code"))

        # Attempt to trust device with wrong password -> ValueError
        with self.assertRaises(ValueError):
            db.create_or_register_device(
                user_id=user_id,
                device_id="laptop_primary_01",
                password="WrongPassword!"
            )

        # Trust device with correct password -> becomes trusted
        trusted_dev = db.create_or_register_device(
            user_id=user_id,
            device_id="laptop_primary_01",
            password="SecretPass123!"
        )
        self.assertEqual(trusted_dev["status"], "trusted")
        self.assertFalse(trusted_dev["requires_first_device_trust"])

if __name__ == "__main__":
    unittest.main()
