import sqlite3
import os
import json
import re
from datetime import datetime, timedelta

DB_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sinbha.db")

def get_connection():
    """Returns a SQLite connection with row dictionary access."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes tables for messages, explicit facts, tasks, and audit logs."""
    conn = get_connection()
    cursor = conn.cursor()

    # Chat messages table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Facts table (explicitly stated user details)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fact TEXT NOT NULL,
        category TEXT DEFAULT 'general',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Tasks table (Step 5 & 6)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        due_date TEXT,
        notes TEXT,
        status TEXT DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Step 6B columns for tasks
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

    # Settings table (persistence, quiet hours)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)
    default_settings = {
        "persistence": "normal",
        "quiet_hours_enabled": "true",
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00"
    }
    for k, v in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # Audit log table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT NOT NULL,
        details TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Pending actions table (e.g. for confirmation of fact deletion)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pending_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_type TEXT NOT NULL,
        target_id INTEGER,
        target_text TEXT,
        details TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()

# ----------------- Message Operations -----------------

def save_message(role: str, content: str):
    """Saves a message to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (role, content, timestamp) VALUES (?, ?, datetime('now', 'localtime'))",
        (role, content)
    )
    conn.commit()
    conn.close()

def get_recent_messages(limit: int = 20):
    """Fetches the last N messages for AI context."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content, timestamp FROM messages ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    # Reverse so they are in chronological order
    return [{"role": r["role"], "content": r["content"], "timestamp": r["timestamp"]} for r in reversed(rows)]

def get_all_messages():
    """Fetches all messages for restoring chat history in the UI."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, role, content, timestamp FROM messages ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r["id"], "role": r["role"], "content": r["content"], "timestamp": r["timestamp"]} for r in rows]

# ----------------- Fact Operations -----------------

def get_all_facts():
    """Fetches all remembered facts."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fact, category, created_at FROM facts ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r["id"], "fact": r["fact"], "category": r["category"], "created_at": r["created_at"]} for r in rows]

def add_fact(fact_text: str, category: str = "general") -> int:
    """Adds a new explicit fact and logs it in the audit table."""
    cleaned = fact_text.strip()
    if not cleaned:
        return 0

    conn = get_connection()
    cursor = conn.cursor()

    # Prevent duplicate facts
    cursor.execute("SELECT id FROM facts WHERE LOWER(fact) = LOWER(?)", (cleaned,))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return existing["id"]

    cursor.execute(
        "INSERT INTO facts (fact, category, created_at) VALUES (?, ?, datetime('now', 'localtime'))",
        (cleaned, category)
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_audit("FACT_ADDED", f"Added fact: '{cleaned}' (Category: {category})")
    return new_id

def update_fact(fact_id: int, new_text: str) -> bool:
    """Updates an existing fact and logs the change."""
    cleaned = new_text.strip()
    if not cleaned:
        return False

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT fact FROM facts WHERE id = ?", (fact_id,))
    old_row = cursor.fetchone()
    if not old_row:
        conn.close()
        return False

    old_text = old_row["fact"]
    cursor.execute("UPDATE facts SET fact = ? WHERE id = ?", (cleaned, fact_id))
    conn.commit()
    conn.close()

    log_audit("FACT_UPDATED", f"Updated fact #{fact_id} from '{old_text}' to '{cleaned}'")
    return True

def delete_fact(fact_id: int) -> bool:
    """Deletes a fact and logs it."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT fact FROM facts WHERE id = ?", (fact_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    deleted_text = row["fact"]
    cursor.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
    conn.commit()
    conn.close()

    log_audit("FACT_DELETED", f"Deleted fact #{fact_id}: '{deleted_text}'")
    return True

def update_or_add_fact(fact_text: str, category: str = "general") -> dict:
    """
    Intelligently adds or updates a fact:
    If a fact with the same subject/attribute exists, it updates it.
    Otherwise adds a new one.
    Returns dict: {'action': 'added'|'updated'|'exists', 'id': fact_id, 'fact': fact_text}
    """
    cleaned = fact_text.strip()
    if not cleaned:
        return {"action": "none", "id": 0, "fact": ""}

    all_facts = get_all_facts()
    lower_new = cleaned.lower()

    # Exact duplicate check
    for f in all_facts:
        if f["fact"].lower() == lower_new:
            return {"action": "exists", "id": f["id"], "fact": f["fact"]}

    # Subject pattern check for update (e.g. name, location, favorite drink)
    subjects = [
        (r"\bname\b", "name"),
        (r"\b(favorite|favourite)\s+(drink|tea|coffee|food|dish|color|colour|movie|song|book|hobby)\b", "favorite"),
        (r"\b(lives\s+in|living\s+in|location|city|from)\b", "location"),
        (r"\b(dog|cat|pet)\b", "pet"),
        (r"\b(works\s+as|job|studies|studying|major)\b", "profession"),
    ]

    for pattern, subj in subjects:
        if re.search(pattern, lower_new):
            for existing in all_facts:
                if re.search(pattern, existing["fact"].lower()):
                    # Match found! Update this existing fact
                    update_fact(existing["id"], cleaned)
                    return {"action": "updated", "id": existing["id"], "fact": cleaned, "old_fact": existing["fact"]}

    # If no existing matching subject, add new
    new_id = add_fact(cleaned, category)
    return {"action": "added", "id": new_id, "fact": cleaned}

# ----------------- Pending Action Operations -----------------

def set_pending_action(action_type: str, target_id: int = None, target_text: str = "", details: str = ""):
    """Sets a pending action requiring user confirmation (e.g., forget fact)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_actions")
    cursor.execute(
        "INSERT INTO pending_actions (action_type, target_id, target_text, details, created_at) VALUES (?, ?, ?, ?, datetime('now', 'localtime'))",
        (action_type, target_id, target_text, details)
    )
    conn.commit()
    conn.close()

def get_pending_action():
    """Gets the current pending action if one exists."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, action_type, target_id, target_text, details, created_at FROM pending_actions ORDER BY id DESC LIMIT 1")
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

def clear_pending_action():
    """Clears any pending confirmation action."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_actions")
    conn.commit()
    conn.close()

def purge_all_data():
    """Wipes all chat messages, facts, and tasks while logging the action."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages")
    cursor.execute("DELETE FROM facts")
    cursor.execute("DELETE FROM tasks")
    conn.commit()
    conn.close()

    log_audit("DATA_PURGED", "User requested complete wipe of messages, facts, and tasks.")

# ----------------- Audit Log Operations -----------------

def log_audit(action: str, details: str = ""):
    """Records an entry in the audit log."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_log (action, details, timestamp) VALUES (?, ?, datetime('now', 'localtime'))",
            (action, details)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Audit log warning: {e}")

def get_audit_logs(limit: int = 50):
    """Fetches recent audit records."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, action, details, timestamp FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r["id"], "action": r["action"], "details": r["details"], "timestamp": r["timestamp"]} for r in rows]

# ----------------- Task & Proposal Operations -----------------

def create_task(
    title: str,
    due_date: str = None,
    notes: str = None,
    status: str = "pending",
    due_time: str = None,
    due_datetime: str = None,
    reminders: list = None
) -> int:
    """Inserts a confirmed task into the database and logs it."""
    cleaned_title = title.strip()
    if not cleaned_title:
        return 0

    reminders_json = json.dumps(reminders) if reminders else None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO tasks 
        (title, due_date, due_time, due_datetime, reminders, notes, status, created_at) 
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))""",
        (cleaned_title, due_date, due_time, due_datetime, reminders_json, notes, status)
    )
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    log_audit("TASK_CONFIRMED", f"Confirmed task #{task_id}: '{cleaned_title}' (Due: {due_datetime or due_date or 'None'})")
    return task_id

def get_all_tasks() -> list:
    """Fetches all tasks, sorted by urgency: overdue first, then upcoming by date/time, then no date, then completed."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, due_date, due_time, due_datetime, reminders, notes, 
               status, last_reminded_at, snoozed_until, created_at 
        FROM tasks ORDER BY id DESC
    """)
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

    # Sort tasks:
    # 0: Pending & Overdue (due_datetime or due_date_iso ASC)
    # 1: Pending & with due_datetime or due_date (ASC)
    # 2: Pending & without due_date (id DESC)
    # 3: Completed (id DESC)
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

def get_pending_tasks_count() -> int:
    """Counts pending tasks."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status = 'pending'")
    row = cursor.fetchone()
    conn.close()
    return row["cnt"] if row else 0

def update_task_status(task_id: int, new_status: str) -> bool:
    """Updates task status ('pending' or 'completed') and logs audit event."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT title, status FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    title = row["title"]
    cursor.execute("UPDATE tasks SET status = ?, snoozed_until = NULL WHERE id = ?", (new_status, task_id))
    conn.commit()
    conn.close()

    if new_status == "completed":
        log_audit("TASK_COMPLETED", f"Completed task #{task_id}: '{title}'")
    elif new_status == "pending":
        log_audit("TASK_REOPENED", f"Reopened task #{task_id}: '{title}'")
    else:
        log_audit("TASK_STATUS_CHANGED", f"Task #{task_id} status changed to {new_status}")

    return True

def delete_task(task_id: int) -> bool:
    """Deletes a task and logs audit event."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    title = row["title"]
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

    log_audit("TASK_DELETED", f"Deleted task #{task_id}: '{title}'")
    return True

def get_task_by_id(task_id: int) -> dict | None:
    """Fetches a single task by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, due_date, due_time, due_datetime, reminders, notes, 
               status, last_reminded_at, snoozed_until, created_at 
        FROM tasks WHERE id = ?
    """, (task_id,))
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

def set_pending_proposal(
    title: str,
    due_date: str = None,
    notes: str = None,
    due_time: str = None,
    due_datetime: str = None,
    suggested_reminders: list = None
) -> int:
    """Sets a pending task proposal requiring user confirmation, and logs it."""
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
    cursor.execute("DELETE FROM pending_actions WHERE action_type = 'task_proposal'")
    cursor.execute(
        "INSERT INTO pending_actions (action_type, target_text, details, created_at) VALUES ('task_proposal', ?, ?, datetime('now', 'localtime'))",
        (cleaned, details_json)
    )
    prop_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_audit("TASK_PROPOSED", f"Proposed task: '{cleaned}' (Due: {due_datetime or due_date or 'None'}, Notes: {notes or 'None'})")
    return prop_id

def get_pending_proposal() -> dict | None:
    """Retrieves current pending task proposal if not expired (>30m)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, action_type, target_text, details, created_at FROM pending_actions WHERE action_type = 'task_proposal' ORDER BY id DESC LIMIT 1"
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
        cursor.execute("DELETE FROM pending_actions WHERE id = ?", (row["id"],))
        conn.commit()
        conn.close()
        log_audit("TASK_CANCELLED", f"Proposal '{row['target_text']}' expired after 30 minutes.")
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

def cancel_pending_proposal(reason: str = "User cancelled") -> bool:
    """Cancels any pending task proposal and logs it."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, target_text FROM pending_actions WHERE action_type = 'task_proposal' ORDER BY id DESC LIMIT 1"
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    title = row["target_text"]
    cursor.execute("DELETE FROM pending_actions WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()

    log_audit("TASK_CANCELLED", f"Cancelled task proposal: '{title}' (Reason: {reason})")
    return True

def confirm_pending_proposal(chosen_reminders: list = None) -> dict | None:
    """Validates and confirms the pending task proposal, saving it to tasks table."""
    prop = get_pending_proposal()
    if not prop:
        return None

    reminders = chosen_reminders if chosen_reminders is not None else prop.get("suggested_reminders", [])
    task_id = create_task(
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
    cursor.execute("DELETE FROM pending_actions WHERE id = ?", (prop["id"],))
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

# ----------------- Settings Operations -----------------

def get_setting(key: str, default: str = None) -> str:
    """Retrieves a setting value."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key: str, value: str) -> None:
    """Sets a setting value."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_all_settings() -> dict:
    """Retrieves all user settings with defaults."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    res = {r["key"]: r["value"] for r in rows}
    defaults = {
        "persistence": "normal",
        "quiet_hours_enabled": "true",
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00"
    }
    for k, v in defaults.items():
        if k not in res:
            res[k] = v
    return res

# ----------------- Reminders & Bird Flight Operations (Step 6B) -----------------

def check_due_reminders(now_dt: datetime = None) -> list:
    """
    Checks for tasks requiring reminder / bird visit right now.
    Rules:
    1. Explicit reminders whose time <= now ALWAYS fire (ignoring quiet hours, requirements 3 & 4).
    2. Overdue / Due today tasks without explicit reminder trigger bird repeat visits
       based on persistence setting (gentle=1440m, normal=30m, persistent=15m),
       unless in quiet hours or snoozed.
    """
    if now_dt is None:
        now_dt = datetime.now()

    now_hm = now_dt.strftime("%H:%M")
    now_iso = now_dt.strftime("%Y-%m-%d %H:%M")
    today_date_str = now_dt.strftime("%Y-%m-%d")

    settings = get_all_settings()
    quiet_enabled = settings.get("quiet_hours_enabled", "true").lower() == "true"
    quiet_start = settings.get("quiet_hours_start", "22:00")
    quiet_end = settings.get("quiet_hours_end", "08:00")
    persistence = settings.get("persistence", "normal").lower()

    # Calculate if currently in quiet hours
    in_quiet = False
    if quiet_enabled:
        if quiet_start > quiet_end:  # Crosses midnight (e.g. 22:00 to 08:00)
            in_quiet = (now_hm >= quiet_start or now_hm < quiet_end)
        else:
            in_quiet = (quiet_start <= now_hm < quiet_end)

    # Persistence intervals in minutes
    interval_minutes = 30
    if persistence == "gentle":
        interval_minutes = 1440  # Once a day
    elif persistence == "persistent":
        interval_minutes = 15

    tasks = get_all_tasks()
    needing_bird = []

    for t in tasks:
        if t["status"] != "pending":
            continue

        # Check if task is currently snoozed or snooze completed
        if t.get("snoozed_until"):
            if t["snoozed_until"] > now_iso:
                # Still in snooze period: do not bother user
                continue
            else:
                # Snooze duration has completed! The bird comes back right now as requested
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

        # 1. Check explicit scheduled reminders
        for rem in reminders:
            r_time = rem.get("time") or rem.get("trigger_at")
            if r_time:
                norm_time = str(r_time).replace("T", " ")[:16]
                if not rem.get("fired") and norm_time <= now_iso:
                    # Requirement 3 & 4: Explicit reminders always fire (even during quiet hours or if missed while app was closed)
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

        # If task has future scheduled reminders, DO NOT trigger premature 'due today' visit!
        # The bird must come ONLY when the reminder time actually arrives.
        has_future_reminders = any(
            not r.get("fired") and (r.get("time") or r.get("trigger_at")) and str(r.get("time") or r.get("trigger_at")).replace("T", " ")[:16] > now_iso
            for r in reminders
        )
        if has_future_reminders:
            continue

        # 2. Check general repeat visit (due today or overdue)
        # Suppressed if currently in quiet hours!
        if in_quiet:
            continue

        is_overdue = t.get("is_overdue", False)
        
        # If due_datetime is specified and is in the future, it is not yet due!
        if t.get("due_datetime") and t["due_datetime"] > now_iso:
            continue

        is_due_today = (t.get("due_date_iso") == today_date_str) or (t.get("due_datetime") and t["due_datetime"].startswith(today_date_str))

        if is_overdue or is_due_today:
            last_rem = t.get("last_reminded_at")
            should_visit = False
            if not last_rem:
                # If newly created today without explicit reminder, don't immediately pop up right after confirming!
                created_str = t.get("created_at")
                if created_str:
                    try:
                        c_dt = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S")
                        # Give at least 4 hours before any unsolicited general repeat check-in on new tasks
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

    # Sort tasks strictly in chronological order by when their reminder was set to fire
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

def mark_reminder_fired(task_id: int, reminder_id: str = None) -> bool:
    """Updates last_reminded_at, marks specific reminder fired, and logs audit."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, reminders FROM tasks WHERE id = ?", (task_id,))
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
        "UPDATE tasks SET reminders = ?, last_reminded_at = ?, snoozed_until = NULL WHERE id = ?",
        (json.dumps(rems), now_str, task_id)
    )
    conn.commit()
    conn.close()

    log_audit("REMINDER_FIRED", f"Reminder fired for task #{task_id}: '{title}'")
    return True

def snooze_task(task_id: int, minutes: int) -> bool:
    """Snoozes task reminders for N minutes and logs audit."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    title = row["title"]
    snooze_until = (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")
    cursor.execute("UPDATE tasks SET snoozed_until = ? WHERE id = ?", (snooze_until, task_id))
    conn.commit()
    conn.close()

    log_audit("REMINDER_SNOOZED", f"Snoozed task #{task_id} ('{title}') for {minutes} minutes (until {snooze_until})")
    return True

def set_pending_task_action(action_type: str, task_id: int, task_title: str) -> int:
    """Sets a pending action to complete or delete a task, requiring user confirmation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_actions WHERE action_type IN ('task_complete', 'task_delete')")
    cursor.execute(
        "INSERT INTO pending_actions (action_type, target_id, target_text, created_at) VALUES (?, ?, ?, datetime('now', 'localtime'))",
        (action_type, task_id, task_title)
    )
    action_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return action_id

def get_pending_task_action() -> dict | None:
    """Retrieves current pending task action (complete or delete) if not expired (>30m)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, action_type, target_id, target_text, created_at FROM pending_actions WHERE action_type IN ('task_complete', 'task_delete') ORDER BY id DESC LIMIT 1"
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
        cursor.execute("DELETE FROM pending_actions WHERE id = ?", (row["id"],))
        conn.commit()
        conn.close()
        log_audit("TASK_CANCELLED", f"Action {row['action_type']} for task #{row['target_id']} expired after 30 minutes.")
        return None

    conn.close()
    return {
        "id": row["id"],
        "action_type": row["action_type"],
        "task_id": row["target_id"],
        "task_title": row["target_text"],
        "created_at": row["created_at"]
    }

def confirm_pending_task_action() -> dict | None:
    """Executes the pending task action (complete or delete) after user confirms."""
    act = get_pending_task_action()
    if not act:
        return None

    action_type = act["action_type"]
    task_id = act["task_id"]
    task_title = act["task_title"]

    success = False
    if action_type == "task_complete":
        success = update_task_status(task_id, "completed")
    elif action_type == "task_delete":
        success = delete_task(task_id)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_actions WHERE id = ?", (act["id"],))
    conn.commit()
    conn.close()

    return {
        "action_type": action_type,
        "task_id": task_id,
        "task_title": task_title,
        "success": success
    }

def cancel_pending_task_action(reason: str = "User cancelled") -> bool:
    """Cancels any pending task complete or delete action."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, action_type, target_text FROM pending_actions WHERE action_type IN ('task_complete', 'task_delete') ORDER BY id DESC LIMIT 1"
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    cursor.execute("DELETE FROM pending_actions WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()
    return True

# Initialize tables immediately on import
init_db()





