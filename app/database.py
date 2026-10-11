import sqlite3
import os
import json
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

DB_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sinbha.db")
ph = PasswordHasher()

def get_connection():
    """Returns a SQLite connection with row dictionary access."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    """Hashes a password with argon2."""
    return ph.hash(password)

def verify_password(hash_str: str, password: str) -> bool:
    """Verifies a plain password against an argon2 hash."""
    try:
        return ph.verify(hash_str, password)
    except (VerifyMismatchError, VerificationError, Exception):
        return False

def init_db():
    """Initializes tables for users, sessions, login attempts, settings, tasks, and messages."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Users table (Step 9)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        emergency_stopped INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Sessions table (httpOnly secure cookie sessions)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_token TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL,
        expires_at DATETIME NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 3. Rate limiting / login attempts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS login_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        identifier TEXT UNIQUE NOT NULL COLLATE NOCASE,
        failed_count INTEGER DEFAULT 1,
        locked_until DATETIME,
        last_attempt DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 4. User Settings table (per-user persistence, quiet hours, country)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_settings (
        user_id INTEGER NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        PRIMARY KEY (user_id, key),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 5. Core data tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        fact TEXT NOT NULL,
        category TEXT DEFAULT 'general',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT NOT NULL,
        due_date TEXT,
        notes TEXT,
        status TEXT DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT NOT NULL,
        details TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pending_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action_type TEXT NOT NULL,
        target_id INTEGER,
        target_text TEXT,
        details TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Ensure user_id column exists on all tables (migration)
    for table in ["messages", "facts", "tasks", "audit_log", "pending_actions"]:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
        except Exception:
            pass

    # Ensure Step 6B columns on tasks
    for col_name, col_type in [
        ("due_time", "TEXT"),
        ("due_datetime", "TEXT"),
        ("reminders", "TEXT"),
        ("last_reminded_at", "TEXT"),
        ("snoozed_until", "TEXT")
    ]:
        try:
            cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass

    conn.commit()
    conn.close()

# ----------------- User Authentication & Account Operations (Step 9) -----------------

def get_user_count() -> int:
    """Returns total number of registered users."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def check_login_rate_limit(identifier: str) -> tuple[bool, int]:
    """
    Checks if identifier (email or IP) is locked out.
    Returns (is_locked, remaining_seconds).
    Rule: 5 failed attempts locks account for 15 minutes.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT failed_count, locked_until FROM login_attempts WHERE identifier = ?",
        (identifier.strip().lower(),)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return False, 0

    locked_until_str = row["locked_until"]
    if locked_until_str:
        try:
            locked_until = datetime.strptime(locked_until_str, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            if now < locked_until:
                diff = int((locked_until - now).total_seconds())
                return True, max(1, diff)
        except Exception:
            pass

    return False, 0

def record_failed_login(identifier: str) -> int:
    """Records a failed login attempt and locks if >= 5 attempts."""
    clean_id = identifier.strip().lower()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT failed_count, locked_until FROM login_attempts WHERE identifier = ?",
        (clean_id,)
    )
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            "INSERT INTO login_attempts (identifier, failed_count, last_attempt) VALUES (?, 1, ?)",
            (clean_id, now_str)
        )
        conn.commit()
        conn.close()
        return 1

    count = row["failed_count"] + 1
    locked_until = None
    if count >= 5:
        # Lockout for 15 minutes
        lock_dt = datetime.now() + timedelta(minutes=15)
        locked_until = lock_dt.strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute(
        "UPDATE login_attempts SET failed_count = ?, locked_until = ?, last_attempt = ? WHERE identifier = ?",
        (count, locked_until, now_str, clean_id)
    )
    conn.commit()
    conn.close()
    return count

def clear_failed_logins(identifier: str):
    """Clears failed login attempts for identifier upon successful login."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM login_attempts WHERE identifier = ?", (identifier.strip().lower(),))
    conn.commit()
    conn.close()

def create_user(email: str, password: str, is_18: bool = True, agreed_terms: bool = True) -> dict:
    """
    Creates a new user account with argon2 password hash.
    Requirement 5: Moves any pre-existing data (user_id IS NULL) to the first account created.
    """
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email:
        raise ValueError("Please provide a valid email address.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if not is_18:
        raise ValueError("You must be 18 or older to create an account.")
    if not agreed_terms:
        raise ValueError("You must agree to the Terms and Privacy Policy.")

    hashed = hash_password(password)

    conn = get_connection()
    cursor = conn.cursor()

    # Check for duplicate email
    cursor.execute("SELECT id FROM users WHERE email = ?", (clean_email,))
    if cursor.fetchone():
        conn.close()
        raise ValueError("An account with this email already exists. Please log in.")

    # Check if this is the very first user created
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    is_first_user = (total_users == 0)
    is_admin = 1 if is_first_user else 0

    cursor.execute(
        "INSERT INTO users (email, password_hash, is_admin, emergency_stopped) VALUES (?, ?, ?, 0)",
        (clean_email, hashed, is_admin)
    )
    user_id = cursor.lastrowid

    # Requirement 5: Move existing data (chats, facts, tasks) to the first account created!
    if is_first_user:
        cursor.execute("UPDATE messages SET user_id = ? WHERE user_id IS NULL", (user_id,))
        cursor.execute("UPDATE facts SET user_id = ? WHERE user_id IS NULL", (user_id,))
        cursor.execute("UPDATE tasks SET user_id = ? WHERE user_id IS NULL", (user_id,))
        cursor.execute("UPDATE audit_log SET user_id = ? WHERE user_id IS NULL", (user_id,))
        cursor.execute("UPDATE pending_actions SET user_id = ? WHERE user_id IS NULL", (user_id,))

    conn.commit()
    conn.close()

    # Initialize default user settings
    default_settings = {
        "persistence": "normal",
        "quiet_hours_enabled": "true",
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00",
        "country": "US"
    }
    for k, v in default_settings.items():
        set_setting(user_id, k, v)

    log_audit(user_id, "USER_SIGNUP", f"New account registered: '{clean_email}' (Admin: {bool(is_admin)})")
    if is_first_user:
        log_audit(user_id, "DATA_MIGRATED", f"Migrated pre-existing local data to first user #{user_id}")

    return {
        "id": user_id,
        "email": clean_email,
        "is_admin": bool(is_admin),
        "emergency_stopped": False
    }

def authenticate_user(email: str, password: str, client_ip: str = "") -> dict:
    """Authenticates email + password with rate limiting."""
    clean_email = email.strip().lower()

    # Check lockout
    is_locked, secs = check_login_rate_limit(clean_email)
    if is_locked:
        mins = max(1, (secs + 59) // 60)
        raise ValueError(f"Too many failed login attempts. Please try again after {mins} minutes.")

    if client_ip:
        is_locked_ip, secs_ip = check_login_rate_limit(client_ip)
        if is_locked_ip:
            mins_ip = max(1, (secs_ip + 59) // 60)
            raise ValueError(f"Too many failed attempts from your connection. Please wait {mins_ip} minutes.")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, email, password_hash, is_admin, emergency_stopped FROM users WHERE email = ?",
        (clean_email,)
    )
    user_row = cursor.fetchone()
    conn.close()

    if not user_row or not verify_password(user_row["password_hash"], password):
        record_failed_login(clean_email)
        if client_ip:
            record_failed_login(client_ip)
        raise ValueError("Invalid email or password.")

    # Successful login: clear lockout
    clear_failed_logins(clean_email)
    if client_ip:
        clear_failed_logins(client_ip)

    user_dict = {
        "id": user_row["id"],
        "email": user_row["email"],
        "is_admin": bool(user_row["is_admin"]),
        "emergency_stopped": bool(user_row["emergency_stopped"])
    }
    log_audit(user_dict["id"], "USER_LOGIN", f"User logged in: '{clean_email}'")
    return user_dict

def create_session(user_id: int) -> str:
    """Creates a secure session token valid for 14 days."""
    token = secrets.token_hex(32)
    expires_at = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (session_token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires_at)
    )
    conn.commit()
    conn.close()
    return token

def get_user_by_session(token: str) -> Optional[dict]:
    """Retrieves user info from valid session token."""
    if not token:
        return None
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.email, u.is_admin, u.emergency_stopped, s.expires_at 
        FROM sessions s 
        JOIN users u ON s.user_id = u.id 
        WHERE s.session_token = ? AND s.expires_at > ?
    """, (token, now_str))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row["id"],
        "email": row["email"],
        "is_admin": bool(row["is_admin"]),
        "emergency_stopped": bool(row["emergency_stopped"])
    }

def delete_session(token: str):
    """Deletes session (logout)."""
    if not token:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
    conn.commit()
    conn.close()

def delete_user_account(user_id: int):
    """
    Requirement 8: Permanently deletes a user account and all associated data.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM facts WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM pending_actions WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM audit_log WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

# ----------------- Message Operations (Per-User) -----------------

def save_message(user_id: int, role: str, content: str):
    """Saves a message to the database for the logged-in user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (user_id, role, content, timestamp) VALUES (?, ?, ?, datetime('now', 'localtime'))",
        (user_id, role, content)
    )
    conn.commit()
    conn.close()

def get_recent_messages(user_id: int, limit: int = 20):
    """Fetches the last N messages for AI context for the logged-in user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content, timestamp FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"], "timestamp": r["timestamp"]} for r in reversed(rows)]

def get_all_messages(user_id: int):
    """Fetches all messages for restoring chat history in UI for the logged-in user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, role, content, timestamp FROM messages WHERE user_id = ? ORDER BY id ASC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r["id"], "role": r["role"], "content": r["content"], "timestamp": r["timestamp"]} for r in rows]

# ----------------- Fact Operations (Per-User) -----------------

def get_all_facts(user_id: int):
    """Fetches all remembered facts for the logged-in user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fact, category, created_at FROM facts WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r["id"], "fact": r["fact"], "category": r["category"], "created_at": r["created_at"]} for r in rows]

def add_fact(user_id: int, fact_text: str, category: str = "general") -> int:
    """Adds a new explicit fact for the user and logs in audit log."""
    cleaned = fact_text.strip()
    if not cleaned:
        return 0

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM facts WHERE user_id = ? AND LOWER(fact) = LOWER(?)", (user_id, cleaned))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return existing["id"]

    cursor.execute(
        "INSERT INTO facts (user_id, fact, category, created_at) VALUES (?, ?, ?, datetime('now', 'localtime'))",
        (user_id, cleaned, category)
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_audit(user_id, "FACT_ADDED", f"Added fact: '{cleaned}' (Category: {category})")
    return new_id

def update_fact(user_id: int, fact_id: int, new_text: str) -> bool:
    """Updates an existing fact for the logged-in user."""
    cleaned = new_text.strip()
    if not cleaned:
        return False

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT fact FROM facts WHERE id = ? AND user_id = ?", (fact_id, user_id))
    old_row = cursor.fetchone()
    if not old_row:
        conn.close()
        return False

    old_text = old_row["fact"]
    cursor.execute("UPDATE facts SET fact = ? WHERE id = ? AND user_id = ?", (cleaned, fact_id, user_id))
    conn.commit()
    conn.close()

    log_audit(user_id, "FACT_UPDATED", f"Updated fact #{fact_id} from '{old_text}' to '{cleaned}'")
    return True

def delete_fact(user_id: int, fact_id: int) -> bool:
    """Deletes a fact belonging to the logged-in user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT fact FROM facts WHERE id = ? AND user_id = ?", (fact_id, user_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    deleted_text = row["fact"]
    cursor.execute("DELETE FROM facts WHERE id = ? AND user_id = ?", (fact_id, user_id))
    conn.commit()
    conn.close()

    log_audit(user_id, "FACT_DELETED", f"Deleted fact #{fact_id}: '{deleted_text}'")
    return True

def update_or_add_fact(user_id: int, fact_text: str, category: str = "general") -> dict:
    """Intelligently adds or updates a fact for the logged-in user."""
    cleaned = fact_text.strip()
    if not cleaned:
        return {"action": "none", "id": 0, "fact": ""}

    all_facts = get_all_facts(user_id)
    lower_new = cleaned.lower()

    for f in all_facts:
        if f["fact"].lower() == lower_new:
            return {"action": "exists", "id": f["id"], "fact": f["fact"]}

    subjects = [
        (r"\bname\b", "name"),
        (r"\b(favorite|favourite)\s+(drink|tea|coffee|food|dish|color|colour|movie|song|book|hobby)\b", "favorite"),
        (r"\b(lives\s+in|living\s+in|location|city|from)\b", "location"),
        (r"\b(dog|cat|pet)\b", "pet"),
        (r"\b(works\s+as|job|studies|studying|major)\b", "profession"),
    ]

    for pattern, _subj in subjects:
        if re.search(pattern, lower_new):
            for existing in all_facts:
                if re.search(pattern, existing["fact"].lower()):
                    update_fact(user_id, existing["id"], cleaned)
                    return {"action": "updated", "id": existing["id"], "fact": cleaned, "old_fact": existing["fact"]}

    new_id = add_fact(user_id, cleaned, category)
    return {"action": "added", "id": new_id, "fact": cleaned}

# ----------------- Pending Actions & Proposals (Per-User) -----------------

def set_pending_action(user_id: int, action_type: str, target_id: int = None, target_text: str = "", details: str = ""):
    """Sets a pending action for the logged-in user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_actions WHERE user_id = ? AND action_type NOT LIKE 'task%'", (user_id,))
    cursor.execute(
        "INSERT INTO pending_actions (user_id, action_type, target_id, target_text, details, created_at) VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))",
        (user_id, action_type, target_id, target_text, details)
    )
    conn.commit()
    conn.close()

def get_pending_action(user_id: int):
    """Gets the current pending memory action for the user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, action_type, target_id, target_text, details, created_at FROM pending_actions WHERE user_id = ? AND action_type NOT LIKE 'task%' ORDER BY id DESC LIMIT 1",
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "action_type": row["action_type"],
        "target_id": row["target_id"],
        "target_text": row["target_text"],
        "details": row["details"],
        "created_at": row["created_at"]
    }

def clear_pending_action(user_id: int):
    """Clears pending memory confirmation action."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_actions WHERE user_id = ? AND action_type NOT LIKE 'task%'", (user_id,))
    conn.commit()
    conn.close()

def set_pending_proposal(
    user_id: int,
    title: str,
    due_date: str = None,
    notes: str = None,
    due_time: str = None,
    due_datetime: str = None,
    suggested_reminders: list = None
) -> int:
    """Sets a pending task proposal for the logged-in user."""
    cleaned = title.strip()
    details_json = json.dumps({
        "title": cleaned,
        "due_date": due_date,
        "due_time": due_time,
        "due_datetime": due_datetime,
        "suggested_reminders": suggested_reminders or [],
        "notes": notes
    })
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_actions WHERE user_id = ? AND action_type = 'task_proposal'", (user_id,))
    cursor.execute(
        "INSERT INTO pending_actions (user_id, action_type, target_text, details, created_at) VALUES (?, 'task_proposal', ?, ?, datetime('now', 'localtime'))",
        (user_id, cleaned, details_json)
    )
    prop_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_audit(user_id, "TASK_PROPOSED", f"Proposed task: '{cleaned}' (Due: {due_datetime or due_date or 'None'}, Notes: {notes or 'None'})")
    return prop_id

def get_pending_proposal(user_id: int) -> dict | None:
    """Retrieves current pending task proposal for the logged-in user if not expired."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, action_type, target_text, details, created_at FROM pending_actions WHERE user_id = ? AND action_type = 'task_proposal' ORDER BY id DESC LIMIT 1",
        (user_id,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    try:
        created_time = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        elapsed = (datetime.now() - created_time).total_seconds()
    except Exception:
        elapsed = 0

    if elapsed > 1800:
        cursor.execute("DELETE FROM pending_actions WHERE id = ? AND user_id = ?", (row["id"], user_id))
        conn.commit()
        conn.close()
        log_audit(user_id, "TASK_CANCELLED", f"Proposal '{row['target_text']}' expired after 30 minutes.")
        return None

    conn.close()
    details = {}
    if row["details"]:
        try:
            details = json.loads(row["details"])
        except Exception:
            pass

    return {
        "id": row["id"],
        "title": details.get("title", row["target_text"]),
        "due_date": details.get("due_date"),
        "due_time": details.get("due_time"),
        "due_datetime": details.get("due_datetime"),
        "suggested_reminders": details.get("suggested_reminders", []),
        "notes": details.get("notes"),
        "created_at": row["created_at"]
    }

def cancel_pending_proposal(user_id: int, reason: str = "User cancelled") -> bool:
    """Cancels any pending task proposal for this user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, target_text FROM pending_actions WHERE user_id = ? AND action_type = 'task_proposal' ORDER BY id DESC LIMIT 1",
        (user_id,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    title = row["target_text"]
    cursor.execute("DELETE FROM pending_actions WHERE id = ? AND user_id = ?", (row["id"], user_id))
    conn.commit()
    conn.close()

    log_audit(user_id, "TASK_CANCELLED", f"Cancelled task proposal: '{title}' (Reason: {reason})")
    return True

def confirm_pending_proposal(user_id: int, chosen_reminders: list = None) -> dict | None:
    """Confirms pending task proposal for this user."""
    prop = get_pending_proposal(user_id)
    if not prop:
        return None

    reminders = chosen_reminders if chosen_reminders is not None else prop.get("suggested_reminders", [])
    task_id = create_task(
        user_id=user_id,
        title=prop["title"],
        due_date=prop.get("due_date"),
        notes=prop.get("notes"),
        status="pending",
        due_time=prop.get("due_time"),
        due_datetime=prop.get("due_datetime"),
        reminders=reminders
    )

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_actions WHERE id = ? AND user_id = ?", (prop["id"], user_id))
    conn.commit()
    conn.close()

    return {
        "id": task_id,
        "title": prop["title"],
        "due_date": prop.get("due_date"),
        "due_time": prop.get("due_time"),
        "due_datetime": prop.get("due_datetime"),
        "reminders": reminders,
        "notes": prop.get("notes"),
        "status": "pending"
    }

def set_pending_task_action(user_id: int, action_type: str, task_id: int, task_title: str) -> int:
    """Sets a pending task action (complete or delete) for this user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_actions WHERE user_id = ? AND action_type IN ('task_complete', 'task_delete')", (user_id,))
    cursor.execute(
        "INSERT INTO pending_actions (user_id, action_type, target_id, target_text, created_at) VALUES (?, ?, ?, ?, datetime('now', 'localtime'))",
        (user_id, action_type, task_id, task_title)
    )
    act_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return act_id

def get_pending_task_action(user_id: int) -> dict | None:
    """Gets current pending task action for this user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, action_type, target_id, target_text, created_at FROM pending_actions WHERE user_id = ? AND action_type IN ('task_complete', 'task_delete') ORDER BY id DESC LIMIT 1",
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "action_type": row["action_type"],
        "task_id": row["target_id"],
        "task_title": row["target_text"],
        "created_at": row["created_at"]
    }

def cancel_pending_task_action(user_id: int, reason: str = "User cancelled") -> bool:
    """Cancels pending task action for this user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_actions WHERE user_id = ? AND action_type IN ('task_complete', 'task_delete')", (user_id,))
    conn.commit()
    conn.close()
    return True

def confirm_pending_task_action(user_id: int) -> dict | None:
    """Confirms pending task action (complete or delete) for this user."""
    act = get_pending_task_action(user_id)
    if not act:
        return None

    task_id = act["task_id"]
    action_type = act["action_type"]

    if action_type == "task_complete":
        update_task_status(user_id, task_id, "completed")
    elif action_type == "task_delete":
        delete_task(user_id, task_id)

    cancel_pending_task_action(user_id, reason="Action confirmed")
    return act

# ----------------- Task Operations (Per-User) -----------------

def create_task(
    user_id: int,
    title: str,
    due_date: str = None,
    notes: str = None,
    status: str = "pending",
    due_time: str = None,
    due_datetime: str = None,
    reminders: list = None
) -> int:
    """Inserts a task for the logged-in user and logs audit."""
    cleaned_title = title.strip()
    if not cleaned_title:
        return 0

    reminders_json = json.dumps(reminders) if reminders else None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO tasks 
        (user_id, title, due_date, due_time, due_datetime, reminders, notes, status, created_at) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))""",
        (user_id, cleaned_title, due_date, due_time, due_datetime, reminders_json, notes, status)
    )
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_audit(user_id, "TASK_CONFIRMED", f"Confirmed task #{task_id}: '{cleaned_title}' (Due: {due_datetime or due_date or 'None'})")
    return task_id

def get_all_tasks(user_id: int) -> list:
    """Fetches all tasks for the logged-in user, sorted by urgency."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, title, due_date, due_time, due_datetime, reminders, notes, 
               status, last_reminded_at, snoozed_until, created_at 
        FROM tasks WHERE user_id = ? ORDER BY id DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()

    now = datetime.now()
    now_hm_str = now.strftime("%Y-%m-%d %H:%M")
    today_str = now.strftime("%Y-%m-%d")
    tasks = []

    for r in rows:
        due = r["due_date"]
        due_time = r["due_time"]
        due_datetime = r["due_datetime"]
        status = r["status"]
        is_overdue = False
        due_date_iso = ""

        if due_datetime:
            if status == "pending" and due_datetime < now_hm_str:
                is_overdue = True
            m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", due_datetime)
            if m:
                due_date_iso = m.group(1)
        elif due:
            m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", due)
            if m:
                due_date_iso = m.group(1)
                if status == "pending" and due_date_iso < today_str:
                    is_overdue = True

        rems = []
        if r["reminders"]:
            try:
                rems = json.loads(r["reminders"])
            except Exception:
                pass

        tasks.append({
            "id": r["id"],
            "user_id": r["user_id"],
            "title": r["title"],
            "due_date": due,
            "due_time": due_time,
            "due_datetime": due_datetime,
            "reminders": rems,
            "due_date_iso": due_date_iso,
            "notes": r["notes"],
            "status": status,
            "is_overdue": is_overdue,
            "last_reminded_at": r["last_reminded_at"],
            "snoozed_until": r["snoozed_until"],
            "created_at": r["created_at"]
        })

    def task_sort_key(t):
        if t["status"] == "completed":
            return (3, 999999 - t["id"])
        if t["is_overdue"]:
            return (0, t["due_datetime"] or t["due_date_iso"] or "9999-99-99")
        if t["due_datetime"]:
            return (1, t["due_datetime"])
        if t["due_date_iso"]:
            return (1, t["due_date_iso"])
        return (2, 999999 - t["id"])

    tasks.sort(key=task_sort_key)
    return tasks

def get_task_by_id(user_id: int, task_id: int) -> dict | None:
    """Retrieves a single task belonging to this user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, title, due_date, due_time, due_datetime, reminders, 
               notes, status, last_reminded_at, snoozed_until, created_at 
        FROM tasks WHERE id = ? AND user_id = ?
    """, (task_id, user_id))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None

    rems = []
    if row["reminders"]:
        try:
            rems = json.loads(row["reminders"])
        except Exception:
            pass

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "due_date": row["due_date"],
        "due_time": row["due_time"],
        "due_datetime": row["due_datetime"],
        "reminders": rems,
        "notes": row["notes"],
        "status": row["status"],
        "last_reminded_at": row["last_reminded_at"],
        "snoozed_until": row["snoozed_until"],
        "created_at": row["created_at"]
    }

def update_task_status(user_id: int, task_id: int, new_status: str) -> bool:
    """Updates status for a task belonging to this user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    title = row["title"]
    cursor.execute("UPDATE tasks SET status = ?, snoozed_until = NULL WHERE id = ? AND user_id = ?", (new_status, task_id, user_id))
    conn.commit()
    conn.close()

    if new_status == "completed":
        log_audit(user_id, "TASK_COMPLETED", f"Completed task #{task_id}: '{title}'")
    elif new_status == "pending":
        log_audit(user_id, "TASK_REOPENED", f"Reopened task #{task_id}: '{title}'")
    else:
        log_audit(user_id, "TASK_STATUS_CHANGED", f"Task #{task_id} status changed to {new_status}")

    return True

def delete_task(user_id: int, task_id: int) -> bool:
    """Deletes a task belonging to this user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    title = row["title"]
    cursor.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    conn.commit()
    conn.close()

    log_audit(user_id, "TASK_DELETED", f"Deleted task #{task_id}: '{title}'")
    return True

def get_pending_tasks_count(user_id: int) -> int:
    """Counts pending tasks for this user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'pending'", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

# ----------------- Settings & STOP State Operations (Per-User) -----------------

def get_setting(user_id: int, key: str, default: str = None) -> str:
    """Retrieves a setting value for this user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM user_settings WHERE user_id = ? AND key = ?", (user_id, key))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(user_id: int, key: str, value: str) -> None:
    """Sets a setting value for this user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO user_settings (user_id, key, value) VALUES (?, ?, ?)",
        (user_id, key, str(value))
    )
    conn.commit()
    conn.close()

def get_all_settings(user_id: int) -> dict:
    """Retrieves all settings for this user with defaults."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM user_settings WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    res = {r["key"]: r["value"] for r in rows}
    defaults = {
        "persistence": "normal",
        "quiet_hours_enabled": "true",
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00",
        "country": "US"
    }
    for k, v in defaults.items():
        if k not in res:
            res[k] = v
    return res

def set_emergency_stopped(user_id: int, stopped: bool) -> None:
    """Sets the per-user emergency STOP state."""
    val = 1 if stopped else 0
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET emergency_stopped = ? WHERE id = ?", (val, user_id))
    conn.commit()
    conn.close()

def get_emergency_stopped(user_id: int) -> bool:
    """Checks if emergency STOP is active for this user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT emergency_stopped FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row["emergency_stopped"]) if row else False

# ----------------- Reminders & Bird Flight Operations (Per-User) -----------------

def check_due_reminders(user_id: int, now_dt: datetime = None) -> list:
    """
    Checks for tasks requiring reminder / bird visit right now for this user.
    Rules:
    1. Returns tasks for logged-in user ONLY.
    2. Explicit reminders or expired snoozes always fire.
    3. Future reminders / future due times NEVER trigger premature visits.
    4. Sorted strictly in chronological order ascending.
    """
    if now_dt is None:
        now_dt = datetime.now()

    # Check per-user STOP
    if get_emergency_stopped(user_id):
        return []

    now_hm = now_dt.strftime("%H:%M")
    now_iso = now_dt.strftime("%Y-%m-%d %H:%M")
    today_date_str = now_dt.strftime("%Y-%m-%d")

    settings = get_all_settings(user_id)
    quiet_enabled = settings.get("quiet_hours_enabled", "true").lower() == "true"
    quiet_start = settings.get("quiet_hours_start", "22:00")
    quiet_end = settings.get("quiet_hours_end", "08:00")
    persistence = settings.get("persistence", "normal").lower()

    in_quiet = False
    if quiet_enabled:
        if quiet_start > quiet_end:
            in_quiet = (now_hm >= quiet_start or now_hm < quiet_end)
        else:
            in_quiet = (quiet_start <= now_hm < quiet_end)

    interval_minutes = 30
    if persistence == "gentle":
        interval_minutes = 1440
    elif persistence == "persistent":
        interval_minutes = 15

    tasks = get_all_tasks(user_id)
    needing_bird = []

    for t in tasks:
        if t["status"] != "pending":
            continue

        # Check if task is currently snoozed or snooze completed
        if t.get("snoozed_until"):
            if t["snoozed_until"] > now_iso:
                continue
            else:
                needing_bird.append({
                    "task": t,
                    "reason": "snooze_expired",
                    "reminder_id": None,
                    "reminder_label": "Snooze Finished",
                    "is_explicit": True,
                    "warm_message": f"🕊️ Checking back in on '{t['title']}' as requested 🌸"
                })
                continue

        reminders = t.get("reminders") or []
        explicit_fired_now = False

        for rem in reminders:
            r_time = rem.get("time") or rem.get("trigger_at")
            if r_time:
                norm_time = str(r_time).replace("T", " ")[:16]
                if not rem.get("fired") and norm_time <= now_iso:
                    needing_bird.append({
                        "task": t,
                        "reason": "explicit_reminder",
                        "reminder_id": rem.get("id"),
                        "reminder_label": rem.get("label", "Task Reminder"),
                        "is_explicit": True,
                        "warm_message": f"A gentle reminder for you: '{t['title']}' is coming up 🌸 Take your time, you've got this."
                    })
                    explicit_fired_now = True
                    break

        if explicit_fired_now:
            continue

        has_future_reminders = any(
            not r.get("fired") and (r.get("time") or r.get("trigger_at")) and str(r.get("time") or r.get("trigger_at")).replace("T", " ")[:16] > now_iso
            for r in reminders
        )
        if has_future_reminders:
            continue

        if in_quiet:
            continue

        is_overdue = t.get("is_overdue", False)
        if t.get("due_datetime") and t["due_datetime"] > now_iso:
            continue

        is_due_today = (t.get("due_date_iso") == today_date_str) or (t.get("due_datetime") and t["due_datetime"].startswith(today_date_str))

        if is_overdue or is_due_today:
            last_rem = t.get("last_reminded_at")
            should_visit = False
            if not last_rem:
                created_str = t.get("created_at")
                if created_str:
                    try:
                        c_dt = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S")
                        if (now_dt - c_dt).total_seconds() < 14400:
                            should_visit = False
                        else:
                            should_visit = True
                    except Exception:
                        should_visit = False
                else:
                    should_visit = False
            else:
                try:
                    last_dt = datetime.strptime(last_rem, "%Y-%m-%d %H:%M:%S")
                    if (now_dt - last_dt).total_seconds() >= (interval_minutes * 60):
                        should_visit = True
                except Exception:
                    should_visit = True

            if should_visit:
                reason = "overdue" if is_overdue else "due_today"
                warm_msg = (
                    f"A gentle check-in: '{t['title']}' was due earlier. Whenever you're ready, I'm right here 🌸"
                    if is_overdue
                    else f"Friendly hello! '{t['title']}' is on your list for today. No rush, you've got this 🌸"
                )
                needing_bird.append({
                    "task": t,
                    "reason": reason,
                    "reminder_id": None,
                    "reminder_label": "Overdue Task" if is_overdue else "Due Today",
                    "is_explicit": False,
                    "warm_message": warm_msg
                })

    def reminder_sort_key(item):
        t = item["task"]
        if item.get("reason") == "snooze_expired" and t.get("snoozed_until"):
            return (0, t["snoozed_until"])
        if item.get("is_explicit") and item.get("reminder_id"):
            for r in t.get("reminders") or []:
                if r.get("id") == item["reminder_id"]:
                    return (0, str(r.get("time") or r.get("trigger_at") or "")[:16])
        if t.get("due_datetime"):
            return (1, t["due_datetime"])
        if t.get("due_date_iso"):
            return (2, t["due_date_iso"])
        return (3, t.get("created_at") or "9999")

    needing_bird.sort(key=reminder_sort_key)
    return needing_bird

def mark_reminder_fired(user_id: int, task_id: int, reminder_id: str = None) -> bool:
    """Updates last_reminded_at, marks specific reminder fired, and logs audit."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, reminders FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    title = row["title"]
    rems = []
    if row["reminders"]:
        try:
            rems = json.loads(row["reminders"])
        except Exception:
            pass

    for r in rems:
        if reminder_id and r.get("id") == reminder_id:
            r["fired"] = True
        elif not reminder_id:
            r["fired"] = True

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE tasks SET reminders = ?, last_reminded_at = ?, snoozed_until = NULL WHERE id = ? AND user_id = ?",
        (json.dumps(rems), now_str, task_id, user_id)
    )
    conn.commit()
    conn.close()

    log_audit(user_id, "REMINDER_FIRED", f"Reminder fired for task #{task_id}: '{title}'")
    return True

def snooze_task(user_id: int, task_id: int, minutes: int) -> bool:
    """Snoozes task reminders for N minutes for this user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    title = row["title"]
    snooze_until = (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")
    cursor.execute("UPDATE tasks SET snoozed_until = ? WHERE id = ? AND user_id = ?", (snooze_until, task_id, user_id))
    conn.commit()
    conn.close()

    log_audit(user_id, "REMINDER_SNOOZED", f"Snoozed task #{task_id} ('{title}') for {minutes} minutes (until {snooze_until})")
    return True

# ----------------- Audit Log & Purge Operations (Per-User) -----------------

def log_audit(user_id: Optional[int], action: str, details: str = ""):
    """Records an entry in the audit log for a specific user."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_log (user_id, action, details, timestamp) VALUES (?, ?, ?, datetime('now', 'localtime'))",
            (user_id, action, details)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Audit log warning: {e}")

def get_audit_logs(user_id: int, limit: int = 50):
    """Fetches recent audit records for the logged-in user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, user_id, action, details, timestamp FROM audit_log WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r["id"], "user_id": r["user_id"], "action": r["action"], "details": r["details"], "timestamp": r["timestamp"]} for r in rows]

def purge_all_data(user_id: int):
    """Wipes all chat messages, facts, and tasks for the logged-in user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM facts WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    log_audit(user_id, "DATA_PURGED", "User requested complete wipe of their messages, facts, and tasks.")

# Automatically run schema initialization on import
init_db()
