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

    # Tasks table (ready for Step 5 & 6)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        due_date TEXT,
        status TEXT DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

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

# Initialize tables immediately on import
init_db()





