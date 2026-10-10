import sqlite3
import os
import json
import re
from datetime import datetime

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
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN notes TEXT")
    except Exception:
        pass

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

def create_task(title: str, due_date: str = None, notes: str = None, status: str = "pending") -> int:
    """Inserts a confirmed task into the database and logs it."""
    cleaned_title = title.strip()
    if not cleaned_title:
        return 0
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (title, due_date, notes, status, created_at) VALUES (?, ?, ?, ?, datetime('now', 'localtime'))",
        (cleaned_title, due_date, notes, status)
    )
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    log_audit("TASK_CONFIRMED", f"Confirmed task #{task_id}: '{cleaned_title}' (Due: {due_date or 'None'})")
    return task_id

def get_all_tasks() -> list:
    """Fetches all tasks, sorted by urgency: overdue first, then upcoming by date, then no date, then completed."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, due_date, notes, status, created_at FROM tasks ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    today_str = datetime.now().strftime("%Y-%m-%d")
    tasks = []

    for r in rows:
        due = r["due_date"]
        status = r["status"]
        is_overdue = False
        due_date_iso = ""

        if due:
            m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", due)
            if m:
                due_date_iso = m.group(1)
                if status == "pending" and due_date_iso < today_str:
                    is_overdue = True

        tasks.append({
            "id": r["id"],
            "title": r["title"],
            "due_date": due,
            "due_date_iso": due_date_iso,
            "notes": r["notes"],
            "status": status,
            "is_overdue": is_overdue,
            "created_at": r["created_at"]
        })

    # Sort tasks:
    # 0: Pending & Overdue (due_date_iso ASC)
    # 1: Pending & with due_date (due_date_iso ASC)
    # 2: Pending & without due_date (id DESC)
    # 3: Completed (id DESC)
    def task_sort_key(t):
        if t["status"] == "completed":
            return (3, 999999 - t["id"])
        if t["is_overdue"]:
            return (0, t["due_date_iso"] or "9999-99-99")
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
    cursor.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))
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
    cursor.execute("SELECT id, title, due_date, notes, status, created_at FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "title": row["title"],
        "due_date": row["due_date"],
        "notes": row["notes"],
        "status": row["status"],
        "created_at": row["created_at"]
    }

def set_pending_proposal(title: str, due_date: str = None, notes: str = None) -> int:
    """Sets a pending task proposal requiring user confirmation, and logs it."""
    cleaned = title.strip()
    details_json = json.dumps({
        "title": cleaned,
        "due_date": due_date,
        "notes": notes
    })
    conn = get_connection()
    cursor = conn.cursor()
    # Remove previous pending proposals
    cursor.execute("DELETE FROM pending_actions WHERE action_type = 'task_proposal'")
    cursor.execute(
        "INSERT INTO pending_actions (action_type, target_text, details, created_at) VALUES ('task_proposal', ?, ?, datetime('now', 'localtime'))",
        (cleaned, details_json)
    )
    prop_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_audit("TASK_PROPOSED", f"Proposed task: '{cleaned}' (Due: {due_date or 'None'}, Notes: {notes or 'None'})")
    return prop_id

def get_pending_proposal() -> dict | None:
    """
    Retrieves the current pending task proposal if one exists and has not expired.
    Proposals expire after 30 minutes (1800 seconds).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, action_type, target_text, details, created_at FROM pending_actions WHERE action_type = 'task_proposal' ORDER BY id DESC LIMIT 1"
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    # Check 30-minute expiry (1800 seconds)
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

def confirm_pending_proposal() -> dict | None:
    """Validates and confirms the pending task proposal, saving it to tasks table."""
    prop = get_pending_proposal()
    if not prop:
        return None

    task_id = create_task(
        title=prop["title"],
        due_date=prop.get("due_date"),
        notes=prop.get("notes"),
        status="pending"
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
        "notes": prop.get("notes"),
        "status": "pending"
    }

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





