import os
import sys
import unittest
from unittest import mock
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

class TestAlarmReminders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.temp_db = os.path.join(cls.temp_dir, "test_alarm_reminders.db")
        db.set_engine_url(f"sqlite:///{cls.temp_db}")
        db.init_db()

        cls.client = TestClient(app)

        # Create test user & full user session
        user = db.create_user("alarm_tester@example.com", "Password123!", is_18=True, agreed_terms=True)
        cls.user_id = user["id"]
        cls.token = db.create_session(cls.user_id)
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    def test_01_user_display_name_resolution(self):
        # 1. Default fallback without custom name
        name = db.get_user_display_name(self.user_id)
        # Should derive from email "alarm_tester" -> "Alarm" or fallback
        self.assertIn(name.lower(), ["alarm", "alarm_tester", "alarm tester", "friend"])

        # 2. Set custom user_display_name in settings
        db.set_setting(self.user_id, "user_display_name", "Karan")
        name = db.get_user_display_name(self.user_id)
        self.assertEqual(name, "Karan")

        # 3. If settings is cleared, falls back to facts if present
        db.set_setting(self.user_id, "user_display_name", "")
        db.add_fact(self.user_id, "The user's name is Maya", category="identity")
        name = db.get_user_display_name(self.user_id)
        self.assertEqual(name, "Maya")

    def test_02_alarm_settings_crud(self):
        # Update settings via API
        payload = {
            "persistence": "normal",
            "quiet_hours_enabled": "true",
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
            "reminder_sound_mode": "voice_then_tone",
            "reminder_custom_song_uri": "content://media/external/audio/media/1234",
            "user_display_name": "Teja",
            "dnd_allow_alarms": "true"
        }
        res = self.client.post("/api/settings", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)

        # Verify saved settings via GET /api/settings
        res_get = self.client.get("/api/settings", headers=self.headers)
        self.assertEqual(res_get.status_code, 200)
        data = res_get.json().get("settings", {})
        self.assertEqual(data.get("reminder_sound_mode"), "voice_then_tone")
        self.assertEqual(data.get("reminder_custom_song_uri"), "content://media/external/audio/media/1234")
        self.assertEqual(data.get("user_display_name"), "Teja")
        self.assertEqual(str(data.get("dnd_allow_alarms")).lower(), "true")

    def test_03_check_due_reminders_and_speech_generation(self):
        # Set user display name to Teja
        db.set_setting(self.user_id, "user_display_name", "Teja")
        db.set_setting(self.user_id, "reminder_sound_mode", "tts_voice")

        # Add an overdue task with an explicit scheduled reminder in the past
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        past_date_str = past_time.strftime("%Y-%m-%d")
        past_time_str = past_time.strftime("%H:%M")

        task_id = db.create_task(
            user_id=self.user_id,
            title="Drink a glass of water",
            due_date=past_date_str,
            due_time=past_time_str,
            chosen_reminders=[{
                "id": "rem_1",
                "label": "Drink Water Reminder",
                "time": f"{past_date_str} {past_time_str}",
                "sound_mode": "tts_voice"
            }]
        )
        self.assertIsNotNone(task_id)

        due_items = db.check_due_reminders(self.user_id)
        self.assertTrue(len(due_items) > 0)

        found = next((item for item in due_items if item.get("task", {}).get("id") == task_id), None)
        self.assertIsNotNone(found)
        self.assertEqual(found.get("user_name"), "Teja")
        self.assertEqual(found.get("sound_mode"), "tts_voice")
        self.assertEqual(found.get("speech_text"), "Hey Teja, it is time to Drink a glass of water")

    def test_04_upcoming_reminders_endpoint(self):
        future_time = datetime.now(timezone.utc) + timedelta(minutes=30)
        future_date_str = future_time.strftime("%Y-%m-%d")
        future_time_str = future_time.strftime("%H:%M")

        task_id = db.create_task(
            user_id=self.user_id,
            title="Review quarterly report",
            due_date=future_date_str,
            due_time=future_time_str,
            chosen_reminders=[{
                "id": "rem_report",
                "label": "Report Reminder",
                "time": f"{future_date_str} {future_time_str}",
                "sound_mode": "tts_voice"
            }]
        )

        res = self.client.get("/api/reminders/upcoming", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        items = res.json().get("reminders", [])
        self.assertTrue(len(items) > 0)

        matched = next((x for x in items if "Review quarterly report" in x.get("task_title", "")), None)
        self.assertIsNotNone(matched)
        self.assertEqual(matched.get("user_name"), "Teja")
        self.assertIn("Review quarterly report", matched.get("speech_text", ""))
        self.assertEqual(matched.get("sound_mode"), "tts_voice")

    @mock.patch("app.agent_loop._call_llm_with_tools")
    def test_05_ai_chat_intent_sound_mode_detection(self, mock_llm):
        async def mock_call_llm(messages, tools, creds):
            last_content = messages[-1].get("content", "").lower()
            if "voice" in last_content:
                args = {"title": "submit tax forms", "due_date": "5pm"}
            else:
                args = {"title": "call John", "due_date": "in 20 minutes"}
            return {
                "success": True,
                "message": {
                    "role": "assistant",
                    "content": "I'll set that reminder for you 🌸",
                    "tool_calls": [{
                        "id": "tc_test_rem",
                        "type": "function",
                        "function": {"name": "create_task", "arguments": json.dumps(args)}
                    }]
                },
                "finish_reason": "tool_calls"
            }
        mock_llm.side_effect = mock_call_llm

        # Test voice sound mode in chat
        chat_req = {
            "message": "remind me with voice to submit tax forms at 5pm",
            "session_id": "test_session_voice"
        }
        res = self.client.post("/api/chat", json=chat_req, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        proposal = data.get("proposal")
        self.assertIsNotNone(proposal)
        self.assertIn(proposal.get("sound_mode"), ["voice", "tts_voice"])
        suggested = proposal.get("suggested_reminders", [])
        if suggested:
            self.assertIn(suggested[0].get("sound_mode"), ["voice", "tts_voice"])

        # Test custom song sound mode in chat
        chat_req2 = {
            "message": "remind me with a song to call John in 20 minutes",
            "session_id": "test_session_song"
        }
        res2 = self.client.post("/api/chat", json=chat_req2, headers=self.headers)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        prop2 = data2.get("proposal")
        self.assertIsNotNone(prop2)
        self.assertIn(prop2.get("sound_mode"), ["song", "custom_song"])

    def test_06_emergency_stop_suppresses_reminders(self):
        # Activate STOP
        res_stop = self.client.post("/api/stop", headers=self.headers)
        self.assertEqual(res_stop.status_code, 200)

        # Check due reminders - should return empty while STOP is active
        due_items = db.check_due_reminders(self.user_id)
        self.assertEqual(due_items, [])

        # Reset / Resume STOP
        res_resume = self.client.post("/api/resume", headers=self.headers)
        self.assertEqual(res_resume.status_code, 200)

        # Due reminders should be accessible again
        due_items_after = db.check_due_reminders(self.user_id)
        self.assertTrue(len(due_items_after) > 0)

if __name__ == "__main__":
    unittest.main()
