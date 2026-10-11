import os
import sys
import tempfile
import unittest
import datetime
from datetime import timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import inspect
from app import database
from app.database import (
    get_db_session,
    init_db,
    set_engine_url,
    create_task,
    get_all_tasks,
    set_setting,
    get_all_settings,
    create_user,
)
from app.models import Base, Task, Message, User, UserSetting, AuditLog
from app.ai_brain import parse_relative_datetime

class TestStep10PostgresAndUTC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary SQLite database for testing SQLAlchemy 2.0 schema and behavior
        cls.temp_dir = tempfile.mkdtemp()
        cls.temp_db_path = os.path.join(cls.temp_dir, "test_step10.db")
        cls.db_url = f"sqlite:///{cls.temp_db_path.replace(os.sep, '/')}"
        set_engine_url(cls.db_url)
        init_db()

    @classmethod
    def tearDownClass(cls):
        database.engine.dispose()
        if os.path.exists(cls.temp_db_path):
            try:
                os.remove(cls.temp_db_path)
            except Exception:
                pass
        if os.path.exists(cls.temp_dir):
            try:
                os.rmdir(cls.temp_dir)
            except Exception:
                pass

    def test_01_models_and_indexes(self):
        """Verify all SQLAlchemy 2.0 models and compound indexes exist"""
        inspector = inspect(database.engine)
        table_names = inspector.get_table_names()
        expected_tables = ["users", "sessions", "login_attempts", "user_settings", "messages", "tasks", "facts", "audit_log", "pending_actions"]
        for table in expected_tables:
            self.assertIn(table, table_names, f"Table {table} missing from database schema")

        # Verify compound indexes on user_id + time / status
        task_indexes = [idx["name"] for idx in inspector.get_indexes("tasks")]
        self.assertIn("ix_tasks_user_due_utc", task_indexes)
        self.assertIn("ix_tasks_user_status", task_indexes)

        msg_indexes = [idx["name"] for idx in inspector.get_indexes("messages")]
        self.assertIn("ix_messages_user_time", msg_indexes)

        audit_indexes = [idx["name"] for idx in inspector.get_indexes("audit_log")]
        self.assertIn("ix_audit_user_time", audit_indexes)

    def test_02_timezone_setting_per_user(self):
        """Verify user timezone preference storage and retrieval"""
        user = create_user("alice_tz@example.com", "SecurePass123!", timezone_name="America/New_York")
        user_id = user["id"]
        settings = get_all_settings(user_id)
        self.assertEqual(settings.get("timezone"), "America/New_York")

        # Update via set_setting
        set_setting(user_id, "timezone", "Asia/Kolkata")
        updated_settings = get_all_settings(user_id)
        self.assertEqual(updated_settings.get("timezone"), "Asia/Kolkata")

    def test_03_utc_reminder_and_due_date_conversion(self):
        """Verify relative times like 'tomorrow at 8am' convert correctly to UTC based on user timezone"""
        # Test 1: Asia/Kolkata (UTC + 5:30)
        # On 2026-10-11, 08:00 AM in Kolkata is 02:30 AM UTC on the same day
        ref_time = datetime.datetime(2026, 10, 11, 10, 0, 0)
        res_kolkata = parse_relative_datetime("tomorrow at 8am", base_dt=ref_time, user_timezone="Asia/Kolkata")
        self.assertEqual(res_kolkata["due_time"], "08:00")
        self.assertIsNotNone(res_kolkata["due_datetime_utc"])
        self.assertTrue(res_kolkata["due_datetime_utc"].startswith("2026-10-12 02:30"))

        # Test 2: America/New_York (EDT UTC - 4:00 in October)
        # 08:00 AM EDT is 12:00 PM (12:00) UTC
        res_ny = parse_relative_datetime("tomorrow at 8am", base_dt=ref_time, user_timezone="America/New_York")
        self.assertEqual(res_ny["due_time"], "08:00")
        self.assertIsNotNone(res_ny["due_datetime_utc"])
        self.assertTrue(res_ny["due_datetime_utc"].startswith("2026-10-12 12:00"))

    def test_04_tasks_saved_with_utc_timestamp(self):
        """Verify tasks and reminders are saved with due_datetime_utc"""
        user = create_user("bob_tz@example.com", "SecurePass123!", timezone_name="Europe/London")
        user_id = user["id"]
        due_utc = datetime.datetime(2026, 10, 15, 13, 0, 0, tzinfo=timezone.utc)
        task_id = create_task(
            user_id=user_id,
            title="Review project proposal",
            due_date="2026-10-15",
            due_time="14:00",
            due_datetime_utc=due_utc,
            chosen_reminders=[{"id": "15m_before", "time": "2026-10-15 13:45"}]
        )

        tasks = get_all_tasks(user_id=user_id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], task_id)
        self.assertTrue("2026-10-15T13:00:00" in tasks[0]["due_datetime_utc"])

if __name__ == "__main__":
    unittest.main()
