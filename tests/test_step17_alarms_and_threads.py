"""
Step 17 Test Suite: Clock-Grade Alarms, Multi-Thread Chat, and Elephant UI
Validates:
1. Thread CRUD endpoints (/api/threads).
2. Shared global memory across different chat threads.
3. Sound options per user & reminder (alarm_tone, song, spoken_voice, voice_then_tone).
4. Audio & speech payload attached to reminders (/api/reminders/upcoming).
5. AI brain sound option recognition ("remind me with voice", "remind me with a song").
6. Safe fallback when options are unspecified.
"""

import pytest
import sqlite3
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import (
    init_db,
    create_user,
    create_chat_thread,
    get_user_threads,
    rename_chat_thread,
    pin_chat_thread,
    delete_chat_thread,
    save_message,
    get_recent_messages,
    add_fact,
    get_all_facts,
    create_task,
    get_all_settings,
    set_setting,
    get_setting,
    create_session,
    set_engine_url
)
from app.ai_brain import detect_sound_option

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    test_db = str(tmp_path / "test_sinbha_step17.db")
    set_engine_url(f"sqlite:///{test_db}")
    init_db()
    return test_db

def test_ai_brain_detect_sound_option():
    """Verify AI brain accurately detects sound options from user prompts."""
    assert detect_sound_option("remind me with a song to go to the gym") == "song"
    assert detect_sound_option("set a music reminder for 8pm") == "song"
    assert detect_sound_option("remind me with voice to take my medicine") == "spoken_voice"
    assert detect_sound_option("speak to me when it is time to call mom") == "spoken_voice"
    assert detect_sound_option("remind me with tone to drink water") == "alarm_tone"
    assert detect_sound_option("ring a loud bell tone at 7am") == "alarm_tone"
    assert detect_sound_option("remind me to write notes") == "voice_then_tone"

def test_chat_thread_database_crud():
    """Verify ChatThread creation, renaming, pinning, and deletion in SQLite."""
    user = create_user("threads@test.com", "Password123!")
    user_id = user["id"]

    # 1. Create thread
    t1 = create_chat_thread(user_id, "Project Planning")
    assert t1 is not None
    assert t1["title"] == "Project Planning"
    assert t1["is_pinned"] == 0

    t2 = create_chat_thread(user_id, "Gym Notes")
    assert t2 is not None

    # 2. List threads
    threads = get_user_threads(user_id)
    assert len(threads) == 2

    # 3. Pin thread
    pin_chat_thread(user_id, t1["id"], is_pinned=True)
    threads_after_pin = get_user_threads(user_id)
    pinned_t1 = next(t for t in threads_after_pin if t["id"] == t1["id"])
    assert pinned_t1["is_pinned"] == 1

    # 4. Rename thread
    rename_chat_thread(user_id, t2["id"], "Daily Workout Routine")
    threads_after_rename = get_user_threads(user_id)
    renamed_t2 = next(t for t in threads_after_rename if t["id"] == t2["id"])
    assert renamed_t2["title"] == "Daily Workout Routine"

    # 5. Delete thread
    delete_chat_thread(user_id, t1["id"])
    remaining = get_user_threads(user_id)
    assert len(remaining) == 1
    assert remaining[0]["id"] == t2["id"]

def test_messages_filtered_by_thread_with_shared_global_memory():
    """Verify messages isolate by thread while facts remain shared globally."""
    user = create_user("sharedmem@test.com", "Password123!")
    user_id = user["id"]

    t1 = create_chat_thread(user_id, "Chat One")
    t2 = create_chat_thread(user_id, "Chat Two")

    # Save messages in thread 1
    save_message(user_id, "user", "Message in Thread 1", thread_id=t1["id"])
    save_message(user_id, "assistant", "Response in Thread 1", thread_id=t1["id"])

    # Save messages in thread 2
    save_message(user_id, "user", "Message in Thread 2", thread_id=t2["id"])

    # Save global fact
    add_fact(user_id, "User works as a software architect in Bangalore", category="identity")

    # Thread 1 messages
    m1 = get_recent_messages(user_id, thread_id=t1["id"])
    assert len(m1) == 2
    assert m1[0]["content"] == "Message in Thread 1"

    # Thread 2 messages
    m2 = get_recent_messages(user_id, thread_id=t2["id"])
    assert len(m2) == 1
    assert m2[0]["content"] == "Message in Thread 2"

    # Global facts are shared and accessible regardless of thread
    facts = get_all_facts(user_id)
    assert len(facts) == 1
    assert "software architect" in facts[0]["fact"]

def test_sound_options_settings_api():
    """Verify settings endpoint handles sound options, display name, and DND."""
    user = create_user("soundsettings@test.com", "Password123!")
    token = create_session(user["id"])
    headers = {"Authorization": f"Bearer {token}"}

    # Default settings
    res = client.get("/api/settings", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["settings"]["reminder_sound"] == "voice_then_tone"
    assert data["settings"]["allow_alarms_in_dnd"] == "true"

    # Update sound to custom song and set display name
    update_res = client.post("/api/settings", headers=headers, json={
        "reminder_sound": "song",
        "custom_song_uri": "content://media/external/audio/media/42",
        "user_display_name": "Bhanu Teja",
        "allow_alarms_in_dnd": "true"
    })
    assert update_res.status_code == 200

    # Verify updated settings
    verify_res = client.get("/api/settings", headers=headers)
    s = verify_res.json()["settings"]
    assert s["reminder_sound"] == "song"
    assert s["custom_song_uri"] == "content://media/external/audio/media/42"
    assert s["user_display_name"] == "Bhanu Teja"

def test_reminder_payload_attaches_sound_and_speech():
    """Verify /api/reminders/upcoming attaches sound_option, user_name, and spoken_text."""
    user = create_user("alarmpayload@test.com", "Password123!")
    user_id = user["id"]
    token = create_session(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    set_setting(user_id, "user_display_name", "Bhanu")
    set_setting(user_id, "reminder_sound", "voice_then_tone")

    # Create task with a reminder due in future
    create_task(
        user_id=user_id,
        title="Drink water and stretch",
        due_date="2026-10-28",
        due_time="14:00",
        notes="Urgent task",
        chosen_reminders=["2026-10-28 14:00:00"]
    )

    res = client.get("/api/reminders/upcoming", headers=headers)
    assert res.status_code == 200
    reminders = res.json()["reminders"]
    assert len(reminders) >= 1
    rem = reminders[0]
    assert rem["task_title"] == "Drink water and stretch"
    assert rem["sound_option"] == "voice_then_tone"
    assert rem["user_name"] == "Bhanu"
    assert "Drink water and stretch" in rem["spoken_text"]
    assert "Bhanu" in rem["spoken_text"]

def test_api_threads_rest_endpoints():
    """Verify HTTP API endpoints for /api/threads."""
    user = create_user("threadapi@test.com", "Password123!")
    token = create_session(user["id"])
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create thread via POST
    c_res = client.post("/api/threads", headers=headers, json={"title": "University Planning"})
    assert c_res.status_code == 200
    thread_id = c_res.json()["thread"]["id"]

    # 2. List threads via GET
    l_res = client.get("/api/threads", headers=headers)
    assert l_res.status_code == 200
    assert len(l_res.json()["threads"]) == 1

    # 3. Patch thread (pin)
    p_res = client.patch(f"/api/threads/{thread_id}", headers=headers, json={"is_pinned": True})
    assert p_res.status_code == 200
    assert p_res.json()["thread"]["is_pinned"] is True

    # 4. Delete thread
    d_res = client.delete(f"/api/threads/{thread_id}", headers=headers)
    assert d_res.status_code == 200

    # 5. Verify thread_id was deleted
    l_res2 = client.get("/api/threads", headers=headers)
    assert not any(t["id"] == thread_id for t in l_res2.json()["threads"])
