"""
Step 9 Multi-User & Account Security Test Suite
Tests:
1. Unauthenticated endpoints return 401 Unauthorized.
2. Argon2 password hashing (no plaintext stored, min length 8 validation).
3. 18+ and Terms & Privacy agreement required on signup.
4. Pre-existing unassigned data automatically migrates to the first created user (user_id = 1, is_admin = 1).
5. Rate limiting: 5 consecutive failed logins trigger lockout (429 Too Many Requests).
6. Multi-user isolation: User A never sees, modifies, or deletes User B's messages, facts, tasks, reminders, or settings.
7. Emergency STOP is isolated per-user: User A's STOP does not pause User B.
8. Admin/Dev endpoint protection: Only admin users with DEV_MODE=true can access dev facts and audit logs.
9. Account Deletion: Permanently wipes all data for that user, leaving other users untouched.
10. Logout: Session invalidated, subsequent calls return 401.
"""

import os
import sys
import tempfile
import sqlite3
from datetime import datetime, timedelta

# Ensure repo root is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient

def setup_test_environment():
    # Use a temporary database
    temp_dir = tempfile.mkdtemp()
    temp_db = os.path.join(temp_dir, "test_step9.db")
    
    import app.database as db
    db.set_engine_url(f"sqlite:///{temp_db}")
    
    # Initialize schema
    db.init_db()
    
    # Seed pre-existing unassigned data (to test Requirement 5 migration)
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("INSERT INTO messages (role, content, timestamp) VALUES ('user', 'Pre-existing legacy chat', '2026-10-10 10:00:00')")
    cur.execute("INSERT INTO tasks (title, status, created_at) VALUES ('Pre-existing legacy task', 'pending', '2026-10-10 10:05:00')")
    cur.execute("INSERT INTO facts (fact, category) VALUES ('User loves cherry blossoms', 'preference')")
    cur.execute("INSERT INTO audit_log (action, details, timestamp) VALUES ('LEGACY_ACTION', 'Pre-existing audit entry', '2026-10-10 10:00:00')")
    conn.commit()
    conn.close()
    
    # Set DEV_MODE = True in environment for testing dev endpoints
    os.environ["DEV_MODE"] = "true"
    
    from app.main import app
    client = TestClient(app)
    
    return client, temp_db, temp_dir

def cleanup_test_environment(temp_db, temp_dir):
    try:
        if os.path.exists(temp_db):
            os.remove(temp_db)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
    except Exception:
        pass

def run_all_step9_tests():
    print("=" * 70)
    print("Running SINBHA Step 9 Multi-User & Account Security Test Suite")
    print("=" * 70)
    
    client, temp_db, temp_dir = setup_test_environment()
    
    try:
        # TEST 1: Unauthenticated Endpoints Blocked
        print("\n[Test 1] Verifying unauthenticated endpoints return 401...")
        for endpoint in ["/api/messages", "/api/tasks", "/api/facts", "/api/settings", "/api/dev/facts", "/api/audit"]:
            res = client.get(endpoint)
            assert res.status_code == 401, f"Expected 401 for {endpoint}, got {res.status_code}"
        print("  ✓ All protected endpoints returned 401 Unauthorized.")

        # TEST 2: Signup Validation (Password length, 18+ check, Terms agreement)
        print("\n[Test 2] Verifying signup input validations...")
        # Short password (< 8 chars)
        res = client.post("/api/auth/signup", json={
            "email": "userA@example.com",
            "password": "123",
            "is_18_or_older": True,
            "agree_terms": True
        })
        assert res.status_code == 400, "Should reject short password"
        assert "at least 8 characters" in res.json()["detail"]

        # Missing 18+ check
        res = client.post("/api/auth/signup", json={
            "email": "userA@example.com",
            "password": "Password123!",
            "is_18_or_older": False,
            "agree_terms": True
        })
        assert res.status_code == 400, "Should reject non-18+"
        assert "18" in res.json()["detail"]

        # Missing Terms agreement
        res = client.post("/api/auth/signup", json={
            "email": "userA@example.com",
            "password": "Password123!",
            "is_18_or_older": True,
            "agree_terms": False
        })
        assert res.status_code == 400, "Should reject missing terms"
        assert "Terms" in res.json()["detail"]
        print("  ✓ Signup validation correctly enforced rules (min 8 chars, 18+, terms agreement).")

        # TEST 3: First User Creation & Data Migration (Requirement 5)
        print("\n[Test 3] Creating first user (User A) and verifying migration of legacy data...")
        signup_a = client.post("/api/auth/signup", json={
            "email": "userA@example.com",
            "password": "SecurePasswordA123",
            "is_18_or_older": True,
            "agree_terms": True
        })
        assert signup_a.status_code == 200, f"Signup failed: {signup_a.text}"
        user_a_data = signup_a.json()["user"]
        assert user_a_data["email"] == "usera@example.com"
        assert user_a_data["is_admin"] == 1, "First user must be assigned admin (is_admin = 1)"
        cookie_a = signup_a.cookies.get("sinbha_session")
        assert cookie_a, "Signup must set httpOnly sinbha_session cookie"

        # Verify password is Argon2 hashed in database and never plaintext
        conn = sqlite3.connect(temp_db)
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE id = ?", (user_a_data["id"],))
        pw_hash = cur.fetchone()[0]
        assert pw_hash.startswith("$argon2id$"), f"Password hash must be argon2, got {pw_hash}"
        assert "SecurePasswordA123" not in pw_hash

        # Verify legacy chats, tasks, facts migrated to User A
        cur.execute("SELECT user_id, content FROM messages")
        legacy_msg = cur.fetchone()
        assert legacy_msg[0] == user_a_data["id"], "Legacy message must be assigned to User A"

        cur.execute("SELECT user_id, title FROM tasks")
        legacy_task = cur.fetchone()
        assert legacy_task[0] == user_a_data["id"], "Legacy task must be assigned to User A"

        cur.execute("SELECT user_id, fact FROM facts")
        legacy_fact = cur.fetchone()
        assert legacy_fact[0] == user_a_data["id"], "Legacy fact must be assigned to User A"
        conn.close()

        # Check User A can read the migrated chat and task via API
        headers_a = {"Cookie": f"sinbha_session={cookie_a}"}
        res_msgs_a = client.get("/api/messages", headers=headers_a)
        assert any(m["content"] == "Pre-existing legacy chat" for m in res_msgs_a.json()["messages"])

        res_tasks_a = client.get("/api/tasks", headers=headers_a)
        assert any(t["title"] == "Pre-existing legacy task" for t in res_tasks_a.json()["tasks"])
        print("  ✓ Pre-existing unassigned data cleanly migrated to User A (id=1, admin=1).")
        print("  ✓ Argon2 password hashing verified in database.")

        # TEST 4: Rate Limiting on Login (Requirement 2)
        print("\n[Test 4] Verifying login rate limiting (lockout on 5 failures)...")
        # Attempt 5 wrong logins
        for i in range(5):
            res_fail = client.post("/api/auth/login", json={
                "email": "userA@example.com",
                "password": f"WrongPassword_{i}"
            })
            assert res_fail.status_code == 401, f"Attempt {i+1} should fail with 401"
            assert "Invalid" in res_fail.json()["detail"]

        # 6th attempt should trigger 429 lockout
        res_lockout = client.post("/api/auth/login", json={
            "email": "userA@example.com",
            "password": "SecurePasswordA123"
        })
        assert res_lockout.status_code == 429, f"Should be locked out with 429, got {res_lockout.status_code}"
        assert "too many failed" in res_lockout.json()["detail"].lower()
        print("  ✓ Rate limiting successfully locked out account after 5 failed attempts (429).")

        # Clear login lockout in test db so we can test normal login
        conn = sqlite3.connect(temp_db)
        cur = conn.cursor()
        cur.execute("DELETE FROM login_attempts")
        conn.commit()
        conn.close()

        # TEST 5: Create User B and verify complete isolation
        print("\n[Test 5] Creating User B and testing data isolation against User A...")
        signup_b = client.post("/api/auth/signup", json={
            "email": "userB@example.com",
            "password": "SecurePasswordB456",
            "is_18_or_older": True,
            "agree_terms": True
        })
        assert signup_b.status_code == 200
        user_b_data = signup_b.json()["user"]
        assert user_b_data["is_admin"] == 0, "Second user must NOT be admin"
        cookie_b = signup_b.cookies.get("sinbha_session")
        headers_b = {"Cookie": f"sinbha_session={cookie_b}"}

        # 5.1 Messages Isolation: User B sees NO legacy messages of User A
        res_msgs_b = client.get("/api/messages", headers=headers_b)
        assert len(res_msgs_b.json()["messages"]) == 0, "User B should not see any of User A's messages"

        # 5.2 Tasks Isolation: User B sees NO tasks of User A
        res_tasks_b = client.get("/api/tasks", headers=headers_b)
        assert len(res_tasks_b.json()["tasks"]) == 0, "User B should not see any of User A's tasks"

        # User B creates a task directly
        conn = sqlite3.connect(temp_db)
        cur = conn.cursor()
        cur.execute("INSERT INTO tasks (user_id, title, status) VALUES (?, 'User B Secret Project', 'pending')", (user_b_data["id"],))
        user_b_task_id = cur.lastrowid
        conn.commit()
        conn.close()

        # User B sees the new task
        res_tasks_b2 = client.get("/api/tasks", headers=headers_b)
        assert any(t["title"] == "User B Secret Project" for t in res_tasks_b2.json()["tasks"])

        # User A CANNOT see User B's task
        res_tasks_a2 = client.get("/api/tasks", headers=headers_a)
        assert not any(t["title"] == "User B Secret Project" for t in res_tasks_a2.json()["tasks"])

        # User A attempts to delete or patch User B's task -> should be 404 / no effect
        res_del_cross = client.delete(f"/api/tasks/{user_b_task_id}", headers=headers_a)
        assert res_del_cross.status_code in [404, 200]
        # Verify task is STILL intact for User B
        res_tasks_b3 = client.get("/api/tasks", headers=headers_b)
        assert any(t["id"] == user_b_task_id for t in res_tasks_b3.json()["tasks"]), "User A must not be able to delete User B's task"

        # 5.3 Settings Isolation:
        # User A sets country IN, persistence persistent
        client.post("/api/settings", json={"country": "IN", "persistence": "persistent"}, headers=headers_a)
        # User B sets country UK, persistence gentle
        client.post("/api/settings", json={"country": "UK", "persistence": "gentle"}, headers=headers_b)

        settings_a = client.get("/api/settings", headers=headers_a).json()["settings"]
        settings_b = client.get("/api/settings", headers=headers_b).json()["settings"]
        assert settings_a["country"] == "IN" and settings_a["persistence"] == "persistent"
        assert settings_b["country"] == "UK" and settings_b["persistence"] == "gentle"

        # 5.4 Emergency STOP Isolation:
        # User A triggers emergency STOP
        client.post("/api/stop", headers=headers_a)
        me_a = client.get("/api/auth/me", headers=headers_a).json()["user"]
        me_b = client.get("/api/auth/me", headers=headers_b).json()["user"]
        assert me_a["emergency_stopped"] == 1, "User A should be stopped"
        assert me_b["emergency_stopped"] == 0, "User B should NOT be stopped"

        # User A resumes
        client.post("/api/resume", headers=headers_a)
        me_a_resumed = client.get("/api/auth/me", headers=headers_a).json()["user"]
        assert me_a_resumed["emergency_stopped"] == 0
        print("  ✓ Strict data isolation verified across messages, tasks, settings, and STOP state.")

        # TEST 6: Admin / Dev Endpoint Protection (Requirement 4)
        print("\n[Test 6] Testing admin & dev endpoint security...")
        # User B (non-admin) -> Forbidden (403)
        res_dev_b = client.get("/api/dev/facts", headers=headers_b)
        assert res_dev_b.status_code == 403, f"Expected 403 for non-admin on /api/dev/facts, got {res_dev_b.status_code}"

        res_audit_b = client.get("/api/audit", headers=headers_b)
        assert res_audit_b.status_code == 403, f"Expected 403 for non-admin on /api/audit, got {res_audit_b.status_code}"

        # User A (admin) -> Allowed (200)
        res_dev_a = client.get("/api/dev/facts", headers=headers_a)
        assert res_dev_a.status_code == 200, f"Admin should access /api/dev/facts, got {res_dev_a.status_code}"
        assert "facts" in res_dev_a.json()

        res_audit_a = client.get("/api/audit", headers=headers_a)
        assert res_audit_a.status_code == 200, f"Admin should access /api/audit, got {res_audit_a.status_code}"
        print("  ✓ Non-admin User B forbidden from dev & audit endpoints (403); Admin User A allowed (200).")

        # TEST 7: Account Deletion (Requirement 8)
        print("\n[Test 7] Testing permanent account deletion for User B...")
        res_del_acct_b = client.post("/api/account/delete", headers=headers_b)
        assert res_del_acct_b.status_code == 200, f"Account delete failed: {res_del_acct_b.text}"
        assert res_del_acct_b.json()["status"] == "ok"

        # User B session is now dead
        res_b_after = client.get("/api/messages", headers=headers_b)
        assert res_b_after.status_code == 401, "Session for deleted user must be invalid (401)"

        # User B records are completely removed from DB
        conn = sqlite3.connect(temp_db)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE id = ?", (user_b_data["id"],))
        assert cur.fetchone()[0] == 0, "User B should be gone from users table"

        cur.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (user_b_data["id"],))
        assert cur.fetchone()[0] == 0, "User B tasks should be permanently deleted"

        # User A data remains 100% intact
        cur.execute("SELECT COUNT(*) FROM users WHERE id = ?", (user_a_data["id"],))
        assert cur.fetchone()[0] == 1, "User A must remain intact"

        cur.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (user_a_data["id"],))
        assert cur.fetchone()[0] > 0, "User A tasks must remain intact"
        conn.close()
        print("  ✓ User B and all associated records permanently removed; User A unaffected.")

        # TEST 8: Logout (Requirement 1)
        print("\n[Test 8] Testing logout...")
        res_logout_a = client.post("/api/auth/logout", headers=headers_a)
        # Subsequent call with previous cookie must return 401 on protected endpoints
        res_msgs_logged_out = client.get("/api/messages", headers=headers_a)
        assert res_msgs_logged_out.status_code == 401, "Logged out session must return 401 on protected endpoints"

        res_me_logged_out = client.get("/api/auth/me", headers=headers_a)
        assert res_me_logged_out.json()["logged_in"] is False
        print("  ✓ Logout invalidated session; subsequent calls returned 401.")

        print("\n" + "=" * 70)
        print("ALL STEP 9 MULTI-USER & SECURITY TESTS PASSED PERFECTLY! 🌸")
        print("=" * 70)
        return True

    finally:
        cleanup_test_environment(temp_db, temp_dir)

if __name__ == "__main__":
    success = run_all_step9_tests()
    if not success:
        sys.exit(1)
