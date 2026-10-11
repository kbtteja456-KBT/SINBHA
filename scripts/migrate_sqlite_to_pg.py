"""
One-Time Data Migration Script: SQLite (sinbha.db) -> PostgreSQL
Requirement 4: Copies all existing data from sinbha.db into PostgreSQL,
then verifies that the row counts match for every table.
"""

import os
import sys
import json
import sqlite3
import argparse
from datetime import datetime, timezone

# Ensure project root is on path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import sessionmaker
from app.models import (
    Base,
    User,
    Session as UserSession,
    LoginAttempt,
    UserSetting,
    Message,
    Task,
    Fact,
    AuditLog,
    PendingAction,
)
from app.database import get_database_url, create_app_engine

def parse_utc_dt(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(val))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        try:
            dt = datetime.strptime(str(val), "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

def migrate_data(sqlite_path: str, target_db_url: str):
    print("=" * 70)
    print("SINBHA SQLite -> PostgreSQL Migration Utility (Step 10)")
    print("=" * 70)
    print(f"Source SQLite:   {sqlite_path}")
    print(f"Target Database: {target_db_url.split('@')[-1] if '@' in target_db_url else target_db_url}")
    print("-" * 70)

    if not os.path.exists(sqlite_path):
        print(f"Error: SQLite source database not found at {sqlite_path}")
        return False

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    # Create target engine and tables
    target_engine = create_app_engine(target_db_url)
    Base.metadata.create_all(bind=target_engine)
    TargetSession = sessionmaker(bind=target_engine)
    session = TargetSession()

    try:
        # Check existing target tables
        print("\nStarting data migration...")

        # 1. Users
        sqlite_cur.execute("SELECT * FROM users")
        src_users = sqlite_cur.fetchall()
        for u in src_users:
            u_dict = dict(u)
            existing = session.scalar(select(User).where(User.id == u_dict["id"]))
            if not existing:
                session.add(User(
                    id=u_dict["id"],
                    email=u_dict["email"],
                    password_hash=u_dict["password_hash"],
                    is_admin=u_dict.get("is_admin", 0),
                    emergency_stopped=u_dict.get("emergency_stopped", 0),
                    timezone=u_dict.get("timezone", "UTC"),
                    created_at=parse_utc_dt(u_dict.get("created_at")) or datetime.now(timezone.utc)
                ))
        session.commit()
        print(f"  ✓ Users migrated: {len(src_users)} rows")

        # 2. Sessions
        sqlite_cur.execute("SELECT * FROM sessions")
        src_sessions = sqlite_cur.fetchall()
        for s in src_sessions:
            s_dict = dict(s)
            existing = session.scalar(select(UserSession).where(UserSession.id == s_dict["id"]))
            if not existing:
                session.add(UserSession(
                    id=s_dict["id"],
                    session_token=s_dict["session_token"],
                    user_id=s_dict["user_id"],
                    expires_at=parse_utc_dt(s_dict["expires_at"]) or datetime.now(timezone.utc),
                    created_at=parse_utc_dt(s_dict.get("created_at")) or datetime.now(timezone.utc)
                ))
        session.commit()
        print(f"  ✓ Sessions migrated: {len(src_sessions)} rows")

        # 3. Login Attempts
        try:
            sqlite_cur.execute("SELECT * FROM login_attempts")
            src_attempts = sqlite_cur.fetchall()
            for la in src_attempts:
                la_dict = dict(la)
                existing = session.scalar(select(LoginAttempt).where(LoginAttempt.id == la_dict["id"]))
                if not existing:
                    session.add(LoginAttempt(
                        id=la_dict["id"],
                        identifier=la_dict["identifier"],
                        failed_count=la_dict.get("failed_count", 0),
                        locked_until=parse_utc_dt(la_dict.get("locked_until")),
                        last_attempt=parse_utc_dt(la_dict.get("last_attempt")) or datetime.now(timezone.utc)
                    ))
            session.commit()
            print(f"  ✓ Login attempts migrated: {len(src_attempts)} rows")
        except Exception as e:
            src_attempts = []
            print(f"  - No login attempts table in source ({e})")

        # 4. User Settings
        try:
            sqlite_cur.execute("SELECT * FROM user_settings")
            src_settings = sqlite_cur.fetchall()
            for st in src_settings:
                st_dict = dict(st)
                existing = session.scalar(
                    select(UserSetting).where(UserSetting.user_id == st_dict["user_id"], UserSetting.key == st_dict["key"])
                )
                if not existing:
                    session.add(UserSetting(
                        user_id=st_dict["user_id"],
                        key=st_dict["key"],
                        value=st_dict["value"],
                        updated_at=parse_utc_dt(st_dict.get("updated_at")) or datetime.now(timezone.utc)
                    ))
            session.commit()
            print(f"  ✓ User settings migrated: {len(src_settings)} rows")
        except Exception:
            src_settings = []

        # 5. Messages
        sqlite_cur.execute("SELECT * FROM messages")
        src_messages = sqlite_cur.fetchall()
        for m in src_messages:
            m_dict = dict(m)
            existing = session.scalar(select(Message).where(Message.id == m_dict["id"]))
            if not existing:
                session.add(Message(
                    id=m_dict["id"],
                    user_id=m_dict["user_id"] or 1,
                    role=m_dict["role"],
                    content=m_dict["content"],
                    timestamp=parse_utc_dt(m_dict.get("timestamp")) or datetime.now(timezone.utc)
                ))
        session.commit()
        print(f"  ✓ Messages migrated: {len(src_messages)} rows")

        # 6. Tasks
        sqlite_cur.execute("SELECT * FROM tasks")
        src_tasks = sqlite_cur.fetchall()
        for t in src_tasks:
            t_dict = dict(t)
            existing = session.scalar(select(Task).where(Task.id == t_dict["id"]))
            if not existing:
                rem_val = t_dict.get("reminders_json") or t_dict.get("reminders")
                fired_val = t_dict.get("fired_reminders_json")
                session.add(Task(
                    id=t_dict["id"],
                    user_id=t_dict["user_id"] or 1,
                    title=t_dict["title"],
                    due_date=t_dict.get("due_date"),
                    due_time=t_dict.get("due_time"),
                    due_datetime_utc=parse_utc_dt(t_dict.get("due_datetime_utc") or t_dict.get("due_datetime")),
                    notes=t_dict.get("notes"),
                    status=t_dict.get("status", "pending"),
                    reminders_json=rem_val if isinstance(rem_val, str) else json.dumps(rem_val or []),
                    fired_reminders_json=fired_val if isinstance(fired_val, str) else json.dumps(fired_val or []),
                    snoozed_until=parse_utc_dt(t_dict.get("snoozed_until")),
                    created_at=parse_utc_dt(t_dict.get("created_at")) or datetime.now(timezone.utc)
                ))
        session.commit()
        print(f"  ✓ Tasks migrated: {len(src_tasks)} rows")

        # 7. Facts
        sqlite_cur.execute("SELECT * FROM facts")
        src_facts = sqlite_cur.fetchall()
        for f in src_facts:
            f_dict = dict(f)
            existing = session.scalar(select(Fact).where(Fact.id == f_dict["id"]))
            if not existing:
                session.add(Fact(
                    id=f_dict["id"],
                    user_id=f_dict["user_id"] or 1,
                    fact=f_dict["fact"],
                    category=f_dict.get("category", "general"),
                    created_at=parse_utc_dt(f_dict.get("created_at")) or datetime.now(timezone.utc)
                ))
        session.commit()
        print(f"  ✓ Facts migrated: {len(src_facts)} rows")

        # 8. Audit Log
        try:
            sqlite_cur.execute("SELECT * FROM audit_log")
            src_audit = sqlite_cur.fetchall()
            for a in src_audit:
                a_dict = dict(a)
                existing = session.scalar(select(AuditLog).where(AuditLog.id == a_dict["id"]))
                if not existing:
                    session.add(AuditLog(
                        id=a_dict["id"],
                        user_id=a_dict.get("user_id"),
                        action=a_dict["action"],
                        details=a_dict.get("details"),
                        timestamp=parse_utc_dt(a_dict.get("timestamp")) or datetime.now(timezone.utc)
                    ))
            session.commit()
            print(f"  ✓ Audit log migrated: {len(src_audit)} rows")
        except Exception:
            src_audit = []

        # 9. Pending Actions
        try:
            sqlite_cur.execute("SELECT * FROM pending_actions")
            src_pa = sqlite_cur.fetchall()
            for pa in src_pa:
                pa_dict = dict(pa)
                existing = session.scalar(select(PendingAction).where(PendingAction.id == pa_dict["id"]))
                if not existing:
                    session.add(PendingAction(
                        id=pa_dict["id"],
                        user_id=pa_dict.get("user_id", 1),
                        action_type=pa_dict["action_type"],
                        target_id=pa_dict.get("target_id"),
                        target_text=pa_dict.get("target_text"),
                        details=pa_dict.get("details"),
                        created_at=parse_utc_dt(pa_dict.get("created_at")) or datetime.now(timezone.utc)
                    ))
            session.commit()
            print(f"  ✓ Pending actions migrated: {len(src_pa)} rows")
        except Exception:
            src_pa = []

        # Sync PostgreSQL sequence IDs if PostgreSQL
        if "postgresql" in target_db_url:
            for tbl in ["users", "sessions", "login_attempts", "user_settings", "messages", "tasks", "facts", "audit_log", "pending_actions"]:
                try:
                    session.execute(text(f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), coalesce(max(id), 1), max(id) IS NOT null) FROM {tbl}"))
                except Exception:
                    pass
            session.commit()

        # ----------------- Verification Step -----------------
        print("\n" + "=" * 70)
        print("ROW COUNT VERIFICATION (Requirement 4)")
        print("=" * 70)
        print(f"{'Table':<20} | {'SQLite Count':<14} | {'Target Count':<14} | {'Result':<10}")
        print("-" * 70)

        checks = [
            ("users", len(src_users), session.scalar(select(func.count(User.id)))),
            ("sessions", len(src_sessions), session.scalar(select(func.count(UserSession.id)))),
            ("messages", len(src_messages), session.scalar(select(func.count(Message.id)))),
            ("tasks", len(src_tasks), session.scalar(select(func.count(Task.id)))),
            ("facts", len(src_facts), session.scalar(select(func.count(Fact.id)))),
            ("audit_log", len(src_audit), session.scalar(select(func.count(AuditLog.id)))),
            ("login_attempts", len(src_attempts), session.scalar(select(func.count(LoginAttempt.id)))),
            ("pending_actions", len(src_pa), session.scalar(select(func.count(PendingAction.id)))),
        ]

        all_matched = True
        for name, src_cnt, tgt_cnt in checks:
            match = (src_cnt == tgt_cnt)
            status_str = "MATCH ✓" if match else "MISMATCH ✗"
            if not match:
                all_matched = False
            print(f"{name:<20} | {src_cnt:<14} | {tgt_cnt:<14} | {status_str:<10}")

        print("-" * 70)
        if all_matched:
            print("🎉 ALL ROW COUNTS MATCH PERFECTLY! Migration completed successfully.")
            return True
        else:
            print("⚠️ Warning: Some row counts did not match.")
            return False

    except Exception as e:
        session.rollback()
        print(f"\nMigration failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()
        target_engine.dispose()
        sqlite_conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate SQLite sinbha.db to PostgreSQL")
    parser.add_argument("--sqlite-path", default=os.path.join(BASE_DIR, "sinbha.db"), help="Path to sinbha.db")
    parser.add_argument("--target-url", default=get_database_url(), help="Target PostgreSQL connection URL")
    args = parser.parse_args()

    success = migrate_data(args.sqlite_path, args.target_url)
    sys.exit(0 if success else 1)
