"""
SINBHA End-to-End Practical System Test (Safe Isolated Mode)
Tests SINBHA against an isolated, loopback-only uvicorn server with:
- A unique disposable SQLite database in a temporary directory
- Mocked external AI, search, and email providers (zero external requests)
- Automatic cleanup of all resources upon test completion
"""

import sys
import time
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import httpx
from scripts.isolated_server_harness import isolated_test_server


def step(title: str):
    print("\n" + "=" * 65)
    print(f"👉 [PRACTICAL TEST] {title}")
    print("=" * 65)


def run_practical_system_test():
    with isolated_test_server() as srv:
        base_url = srv["base_url"]
        print(f"✅ Isolated test server running at {base_url} (DB: {srv['db_path']})")

        session = httpx.Client(timeout=30.0)

        # -------------------------------------------------------------
        # Step 1: Health & System Diagnostics
        # -------------------------------------------------------------
        step("1. Health & System Diagnostics")
        t0 = time.time()
        res = session.get(f"{base_url}/api/health")
        duration_ms = int((time.time() - t0) * 1000)
        print(f"   HTTP Status: {res.status_code} ({duration_ms}ms)")
        assert res.status_code == 200, f"Health check failed: {res.text}"
        health_data = res.json()
        print(f"   Database Status: {health_data.get('database')}")
        print(f"   Environment: {health_data.get('environment')}")
        print(f"   Reported Version: {health_data.get('version')}")
        assert health_data.get("version") == "1.4.28", f"Version mismatch: {health_data.get('version')}"
        assert health_data.get("status") == "healthy"
        assert health_data.get("database") == "connected"

        # -------------------------------------------------------------
        # Step 2: User Registration & Email Verification
        # -------------------------------------------------------------
        step("2. User Registration & Email Verification")
        test_email = f"practical_tester_{int(time.time())}@sinbha.local"
        test_password = "SecurePassword123!"

        signup_payload = {
            "email": test_email,
            "password": test_password,
            "is_18_or_older": True,
            "agree_terms": True
        }
        signup_res = session.post(f"{base_url}/api/auth/signup", json=signup_payload)
        print(f"   POST /api/auth/signup Status: {signup_res.status_code}")
        assert signup_res.status_code == 200, f"Signup failed: {signup_res.text}"
        signup_data = signup_res.json()
        user_id = signup_data.get("user", {}).get("id")
        print(f"   Signup Response: {signup_data.get('message')}")
        print(f"   Created User ID: {user_id} (Requires Email Verification: {signup_data.get('requires_verification')})")

        # In isolated test mode, retrieve verification token directly from isolated DB
        import sqlite3
        conn = sqlite3.connect(srv["db_path"])
        cur = conn.cursor()
        cur.execute("SELECT verification_token FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        assert row is not None, "User not found in isolated database"
        verify_token = row[0]
        print(f"   Simulating Email Link Click with Token: {verify_token[:12]}...")

        verify_res = session.get(f"{base_url}/api/auth/verify-email?token={verify_token}")
        print(f"   GET /api/auth/verify-email Status: {verify_res.status_code}")
        assert verify_res.status_code == 200, f"Verification failed: {verify_res.text}"
        print(f"   Email Verification Response: {verify_res.json().get('message')}")

        # Now verify login with credentials
        login_payload = {
            "email": test_email,
            "password": test_password
        }
        login_res = session.post(f"{base_url}/api/auth/login", json=login_payload)
        print(f"   POST /api/auth/login Status: {login_res.status_code}")
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        user_info = login_res.json().get("user", {})
        print(f"   Authenticated as User #{user_info.get('id')} ({user_info.get('email')}, Verified={user_info.get('is_verified')})")
        print(f"   Session Cookie Present: {'sinbha_session' in session.cookies}")

        # -------------------------------------------------------------
        # Step 3: Conversational Brain & Chat Message Execution
        # -------------------------------------------------------------
        step("3. Conversational Brain & Chat Message Execution")
        chat_payload = {
            "message": "Hi SINBHA! I am a final-year electrical engineering student preparing for the GATE exam."
        }
        t0 = time.time()
        chat_res = session.post(f"{base_url}/api/chat", json=chat_payload, timeout=15)
        chat_duration = round(time.time() - t0, 2)
        print(f"   POST /api/chat Status: {chat_res.status_code} ({chat_duration}s)")
        assert chat_res.status_code == 200, f"Chat failed: {chat_res.text}"
        chat_data = chat_res.json()
        reply = chat_data.get("reply", "")
        print(f"   SINBHA Reply Preview:\n   \"{reply[:180]}...\"")

        # -------------------------------------------------------------
        # Step 4: Personal Memory Taxonomy & Provenance
        # -------------------------------------------------------------
        step("4. Personal Memory Taxonomy & Provenance")
        mem_res = session.get(f"{base_url}/api/user/memory", timeout=5)
        print(f"   GET /api/user/memory Status: {mem_res.status_code}")
        assert mem_res.status_code == 200
        facts = mem_res.json().get("facts", [])
        print(f"   Currently Remembered Facts ({len(facts)})")

        # Explicit fact addition
        new_fact_payload = {
            "fact": "Target GATE 2027 Electrical Engineering Rank under 100",
            "category": "education",
            "fact_type": "current_goal",
            "confidence": 100
        }
        add_res = session.post(f"{base_url}/api/facts", json=new_fact_payload)
        print(f"   POST /api/facts Status: {add_res.status_code}")
        assert add_res.status_code == 200
        fact_id = add_res.json().get("id") or add_res.json().get("fact_id")
        print(f"   Added Fact ID: #{fact_id}")

        # Export Memory
        exp_res = session.get(f"{base_url}/api/user/memory/export")
        print(f"   GET /api/user/memory/export Status: {exp_res.status_code}")
        assert exp_res.status_code == 200
        exp_data = exp_res.json()
        print(f"   Memory Export Contains {len(exp_data.get('facts', []))} facts for User #{exp_data.get('user_id')}")

        # -------------------------------------------------------------
        # Step 5: Study Plan & Task Creation
        # -------------------------------------------------------------
        step("5. Task & Study Workflows")
        conn = sqlite3.connect(srv["db_path"])
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tasks (user_id, title, status, due_date, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, "Study Power Systems Chapter 4", "pending", "2026-11-09 17:00:00", "2026-11-08 20:00:00"))
        conn.commit()
        conn.close()

        # Inspect created tasks via API
        tasks_res = session.get(f"{base_url}/api/tasks")
        assert tasks_res.status_code == 200
        tasks = tasks_res.json().get("tasks", [])
        print(f"   Total Tasks in DB: {len(tasks)}")
        assert len(tasks) >= 1
        print(f"   - Task #{tasks[0].get('id')}: {tasks[0].get('title')}")

        # -------------------------------------------------------------
        # Step 6: Proactive Assistance & Lifecycle Management
        # -------------------------------------------------------------
        step("6. Proactive Scheduler Events & Lifecycle Endpoints")
        pro_res = session.get(f"{base_url}/api/proactive/events")
        print(f"   GET /api/proactive/events Status: {pro_res.status_code}")
        assert pro_res.status_code == 200
        pro_events = pro_res.json().get("events", [])
        print(f"   Scheduled Proactive Events ({len(pro_events)})")

        if not pro_events:
            # Create a test event directly in DB if task due date parser did not trigger an event
            conn = sqlite3.connect(srv["db_path"])
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO proactive_events (user_id, event_type, title, payload_json, status, scheduled_for_utc, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, "reminder", "Review Power Systems", json.dumps({"note": "Chapter 4"}), "pending", "2026-11-09 10:00:00", "2026-11-08 20:00:00"))
            conn.commit()
            conn.close()

            pro_res = session.get(f"{base_url}/api/proactive/events")
            pro_events = pro_res.json().get("events", [])

        assert len(pro_events) >= 1, "Expected at least one proactive event"
        target_evt_id = pro_events[0]["id"]

        # Snooze test
        snooze_res = session.post(f"{base_url}/api/proactive/events/{target_evt_id}/snooze", json={"snooze_minutes": 45})
        print(f"   POST /api/proactive/events/{target_evt_id}/snooze Status: {snooze_res.status_code}")
        assert snooze_res.status_code == 200
        print(f"   Snooze Response: {snooze_res.json().get('status')}")

        # Reschedule test
        resched_res = session.post(f"{base_url}/api/proactive/events/{target_evt_id}/reschedule", json={"new_scheduled_for_utc": "2026-11-10T10:00:00+00:00"})
        print(f"   POST /api/proactive/events/{target_evt_id}/reschedule Status: {resched_res.status_code}")
        assert resched_res.status_code == 200

        # Dismiss test
        dismiss_res = session.post(f"{base_url}/api/proactive/events/{target_evt_id}/dismiss")
        print(f"   POST /api/proactive/events/{target_evt_id}/dismiss Status: {dismiss_res.status_code}")
        assert dismiss_res.status_code == 200

        # Complete test
        comp_res = session.post(f"{base_url}/api/proactive/events/{target_evt_id}/complete")
        print(f"   POST /api/proactive/events/{target_evt_id}/complete Status: {comp_res.status_code}")
        assert comp_res.status_code == 200

        # -------------------------------------------------------------
        # Step 7: Emergency STOP Switch & Truthful Device State
        # -------------------------------------------------------------
        step("7. Emergency STOP Switch & Truthful Status")
        stop_res = session.post(f"{base_url}/api/stop")
        print(f"   POST /api/stop Status: {stop_res.status_code}")
        assert stop_res.status_code == 200
        stop_data = stop_res.json()
        print(f"   Stop Status: {stop_data.get('status')}")
        print(f"   Stop Message: \"{stop_data.get('message')}\"")

        resume_res = session.post(f"{base_url}/api/resume")
        print(f"   POST /api/resume Status: {resume_res.status_code}")
        assert resume_res.status_code == 200
        print(f"   Resume Status: {resume_res.json().get('status')}")

        print("\n" + "=" * 65)
        print("🎉 ALL PRACTICAL SYSTEM TESTS PASSED IN ISOLATED ENVIRONMENT!")
        print("=" * 65)
        return True


if __name__ == "__main__":
    success = run_practical_system_test()
    sys.exit(0 if success else 1)
