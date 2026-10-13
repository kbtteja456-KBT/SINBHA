"""
SINBHA Database Engine & ORM Layer (Step 10)
Migrated from raw sqlite3 to SQLAlchemy 2.0 models with PostgreSQL & SQLite support.
Supports connection pooling, UTC timestamps, per-user isolation, and rate-limiting.
"""

import os
import json
import secrets
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Tuple

from dotenv import load_dotenv
load_dotenv()

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from sqlalchemy import create_engine, select, update, delete, func, and_, or_, desc
from sqlalchemy.orm import sessionmaker, Session as OrmSession
from sqlalchemy.pool import QueuePool, NullPool

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
    DeviceToken,
    Device,
    utc_now,
)
from app.crypto import encrypt_text, decrypt_text

ph = PasswordHasher()

def hash_password(password: str) -> str:
    """Hashes a password with argon2."""
    return ph.hash(password)

def verify_password(hash_str: str, password: str) -> bool:
    """Verifies a plain password against an argon2 hash."""
    try:
        return ph.verify(hash_str, password)
    except (VerifyMismatchError, VerificationError, Exception):
        return False

# ----------------- Database URL & Connection Setup -----------------

def get_database_url() -> str:
    """
    Reads DATABASE_URL from environment or fallback to SQLite.
    Normalizes PostgreSQL URLs to use modern psycopg (psycopg3).
    Requirement 11: Enforces SSL on PostgreSQL connections.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    is_production = os.getenv("ENV", "development").lower() == "production"

    if not url:
        if is_production:
            raise RuntimeError("CRITICAL: DATABASE_URL is missing in production environment!")
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sinbha.db")
        return f"sqlite:///{db_path}"

    if is_production and url.startswith("sqlite"):
        raise RuntimeError("CRITICAL: SQLite is forbidden in production. PostgreSQL with SSL is required!")

    # Normalize url prefixes for SQLAlchemy 2.0
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    # Requirement 11: Enforce SSL for PostgreSQL connections
    if "postgresql" in url and "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"

    return url

DATABASE_URL = get_database_url()
is_sqlite = DATABASE_URL.startswith("sqlite")

def create_app_engine(db_url: str):
    """Creates SQLAlchemy 2.0 engine with connection pooling."""
    if db_url.startswith("sqlite"):
        return create_engine(
            db_url,
            connect_args={"check_same_thread": False},
        )
    else:
        # PostgreSQL Connection Pooling (Requirement 7)
        return create_engine(
            db_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,
            echo=False,
        )

engine = create_app_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=OrmSession)

@contextmanager
def get_db_session():
    """Context manager for SQLAlchemy transactions."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def set_engine_url(new_url: str):
    """Dynamically reconfigures engine (used for testing or switching DBs)."""
    global engine, SessionLocal, DATABASE_URL, is_sqlite
    DATABASE_URL = new_url
    is_sqlite = DATABASE_URL.startswith("sqlite")
    engine = create_app_engine(new_url)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=OrmSession)

def init_db():
    """Initializes schema tables and indexes."""
    Base.metadata.create_all(bind=engine)

# ----------------- User Authentication & Account Operations (Step 9 & 10) -----------------

def get_user_count() -> int:
    """Returns total registered user count."""
    with get_db_session() as session:
        return session.scalar(select(func.count(User.id))) or 0

def check_login_rate_limit(identifier: str) -> Tuple[bool, int]:
    """
    Checks if identifier (email or IP) is locked out.
    Returns (is_locked, remaining_seconds).
    Rule: 5 failed attempts locks for 15 minutes.
    """
    clean_id = identifier.strip().lower()
    with get_db_session() as session:
        attempt = session.scalar(select(LoginAttempt).where(LoginAttempt.identifier == clean_id))
        if not attempt:
            return False, 0

        now = utc_now()
        if attempt.locked_until:
            # Handle timezone-aware comparison
            locked = attempt.locked_until
            if locked.tzinfo is None:
                locked = locked.replace(tzinfo=timezone.utc)
            if now < locked:
                remaining = int((locked - now).total_seconds())
                return True, max(1, remaining)

        return False, 0

def record_failed_login(identifier: str) -> int:
    """Records a failed login attempt and locks if >= 5 attempts."""
    clean_id = identifier.strip().lower()
    now = utc_now()
    with get_db_session() as session:
        attempt = session.scalar(select(LoginAttempt).where(LoginAttempt.identifier == clean_id))
        if not attempt:
            attempt = LoginAttempt(identifier=clean_id, failed_count=1, last_attempt=now)
            session.add(attempt)
            return 1

        attempt.failed_count += 1
        attempt.last_attempt = now
        if attempt.failed_count >= 5:
            attempt.locked_until = now + timedelta(minutes=15)

        return attempt.failed_count

def clear_failed_logins(identifier: str):
    """Clears failed login records on successful authentication."""
    clean_id = identifier.strip().lower()
    with get_db_session() as session:
        session.execute(delete(LoginAttempt).where(LoginAttempt.identifier == clean_id))

def create_user(
    email: str,
    password: str,
    is_18: bool = True,
    agreed_terms: bool = True,
    timezone_name: str = "UTC"
) -> dict:
    """
    Creates a new user account with argon2 password hash.
    Step 9: Moves any pre-existing data (user_id IS NULL) to the first account created.
    Step 10: Supports per-user timezone (Requirement 6).
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

    with get_db_session() as session:
        # Check duplicate email
        existing = session.scalar(select(User).where(User.email == clean_email))
        if existing:
            raise ValueError("An account with this email already exists. Please log in.")

        total_users = session.scalar(select(func.count(User.id))) or 0
        is_first_user = (total_users == 0)
        is_admin = 1 if is_first_user else 0

        user = User(
            email=clean_email,
            password_hash=hashed,
            is_admin=is_admin,
            emergency_stopped=0,
            timezone=timezone_name or "UTC",
        )
        session.add(user)
        session.flush() # get user.id

        user_id = user.id

        # Migrate pre-existing unassigned legacy data to the first created user
        if is_first_user:
            session.execute(update(Message).where(Message.user_id.is_(None)).values(user_id=user_id))
            session.execute(update(Task).where(Task.user_id.is_(None)).values(user_id=user_id))
            session.execute(update(Fact).where(Fact.user_id.is_(None)).values(user_id=user_id))
            session.execute(update(AuditLog).where(AuditLog.user_id.is_(None)).values(user_id=user_id))
            session.execute(update(PendingAction).where(PendingAction.user_id.is_(None)).values(user_id=user_id))

        # Default settings per user
        defaults = {
            "persistence": "normal",
            "quiet_hours_enabled": "true",
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
            "country": "US",
            "timezone": timezone_name or "UTC"
        }
        for k, v in defaults.items():
            session.add(UserSetting(user_id=user_id, key=k, value=v))

        # Audit log entry
        audit = AuditLog(
            user_id=user_id,
            action="USER_SIGNUP",
            details=f"New account registered: '{clean_email}' (Admin: {bool(is_admin)})"
        )
        session.add(audit)

        if is_first_user:
            session.add(AuditLog(
                user_id=user_id,
                action="DATA_MIGRATED",
                details=f"Migrated pre-existing local data to first user #{user_id}"
            ))

        return {
            "id": user_id,
            "email": clean_email,
            "is_admin": bool(is_admin),
            "emergency_stopped": False,
            "timezone": timezone_name or "UTC"
        }

def authenticate_user(email: str, password: str, client_ip: str = "") -> dict:
    """Authenticates email + password with rate limiting."""
    clean_email = email.strip().lower()

    # Rate limit check on email
    is_locked, secs = check_login_rate_limit(clean_email)
    if is_locked:
        mins = max(1, (secs + 59) // 60)
        raise ValueError(f"Too many failed login attempts. Please try again after {mins} minutes.")

    # Rate limit check on IP
    if client_ip:
        is_locked_ip, secs_ip = check_login_rate_limit(client_ip)
        if is_locked_ip:
            mins_ip = max(1, (secs_ip + 59) // 60)
            raise ValueError(f"Too many failed attempts from your connection. Please wait {mins_ip} minutes.")

    with get_db_session() as session:
        user = session.scalar(select(User).where(User.email == clean_email))
        if not user or not verify_password(user.password_hash, password):
            record_failed_login(clean_email)
            if client_ip:
                record_failed_login(client_ip)
            raise ValueError("Invalid email or password.")

        clear_failed_logins(clean_email)
        if client_ip:
            clear_failed_logins(client_ip)

        session.add(AuditLog(
            user_id=user.id,
            action="USER_LOGIN",
            details=f"User '{clean_email}' successfully logged in."
        ))

        return {
            "id": user.id,
            "email": user.email,
            "is_admin": bool(user.is_admin),
            "emergency_stopped": bool(user.emergency_stopped),
            "timezone": user.timezone or "UTC"
        }

def create_session(user_id: int) -> str:
    """Creates a secure session token expiring in 14 days."""
    token = secrets.token_urlsafe(48)
    expires_at = utc_now() + timedelta(days=14)
    with get_db_session() as session:
        user_sess = UserSession(session_token=token, user_id=user_id, expires_at=expires_at)
        session.add(user_sess)
    return token

def get_user_by_session(token: str) -> Optional[dict]:
    """Resolves active user from session token."""
    if not token:
        return None
    with get_db_session() as session:
        sess = session.scalar(select(UserSession).where(UserSession.session_token == token))
        if not sess:
            return None

        exp = sess.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if utc_now() > exp:
            session.delete(sess)
            return None

        user = sess.user
        if not user:
            return None

        return {
            "id": user.id,
            "email": user.email,
            "is_admin": bool(user.is_admin),
            "emergency_stopped": bool(user.emergency_stopped),
            "timezone": user.timezone or "UTC"
        }

def delete_session(token: str):
    """Deletes a session token on logout."""
    if not token:
        return
    with get_db_session() as session:
        session.execute(delete(UserSession).where(UserSession.session_token == token))

def delete_all_user_sessions(user_id: int):
    """Invalidates all sessions for this user (used on password change)."""
    with get_db_session() as session:
        session.execute(delete(UserSession).where(UserSession.user_id == user_id))

# ----------------- Device Tokens (Mobile Companion) -----------------

MAX_DEVICE_TOKEN_LIFETIME_DAYS = 180

def create_device_token(user_id: int, device_name: str = "Android Companion", days_valid: int = 30) -> dict:
    """
    Creates a dedicated, scoped device token for Android background reminder actions.
    Separated from web sessions, limited strictly to reminder actions.
    """
    token = f"snb_dev_{secrets.token_urlsafe(40)}"
    now = utc_now()
    expires_at = min(now + timedelta(days=days_valid), now + timedelta(days=MAX_DEVICE_TOKEN_LIFETIME_DAYS))
    with get_db_session() as session:
        dev_entry = DeviceToken(
            device_token=token,
            user_id=user_id,
            device_name=device_name,
            scope="reminders_only",
            expires_at=expires_at
        )
        session.add(dev_entry)
    return {
        "device_token": token,
        "expires_at": expires_at.isoformat(),
        "scope": "reminders_only",
        "device_name": device_name
    }

def get_user_by_device_token(token: str) -> Optional[dict]:
    """
    Resolves active user from a device token.
    Enforces rolling expiration and an absolute maximum 180-day lifetime from creation.
    """
    if not token or not token.startswith("snb_dev_"):
        return None
    with get_db_session() as session:
        dt = session.scalar(select(DeviceToken).where(DeviceToken.device_token == token))
        if not dt:
            return None

        now = utc_now()

        # Absolute maximum lifetime from creation (Requirement 2)
        created = dt.created_at
        if created:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            max_limit = created + timedelta(days=MAX_DEVICE_TOKEN_LIFETIME_DAYS)
            if now > max_limit:
                session.delete(dt)
                return None
        else:
            max_limit = now + timedelta(days=MAX_DEVICE_TOKEN_LIFETIME_DAYS)

        exp = dt.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp:
            session.delete(dt)
            return None

        # Rolling renewal: extend by 30 days, capped strictly by 180-day max lifetime
        dt.last_used_at = now
        dt.expires_at = min(now + timedelta(days=30), max_limit)

        user = dt.user
        if not user:
            return None

        return {
            "id": user.id,
            "email": user.email,
            "is_admin": bool(user.is_admin),
            "emergency_stopped": bool(user.emergency_stopped),
            "timezone": user.timezone or "UTC",
            "token_scope": dt.scope,
            "is_device_token": True,
            "device_name": dt.device_name,
            "expires_at": dt.expires_at.isoformat()
        }

def renew_device_token(token: str, days: int = 30) -> Optional[dict]:
    """Extends expiration of an active device token, strictly bounded by 180-day max lifetime."""
    if not token or not token.startswith("snb_dev_"):
        return None
    with get_db_session() as session:
        dt = session.scalar(select(DeviceToken).where(DeviceToken.device_token == token))
        if not dt:
            return None

        now = utc_now()

        # Absolute maximum lifetime from creation (Requirement 2)
        created = dt.created_at
        if created:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            max_limit = created + timedelta(days=MAX_DEVICE_TOKEN_LIFETIME_DAYS)
            if now > max_limit:
                session.delete(dt)
                return None
        else:
            max_limit = now + timedelta(days=MAX_DEVICE_TOKEN_LIFETIME_DAYS)

        exp = dt.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp:
            session.delete(dt)
            return None

        dt.last_used_at = now
        dt.expires_at = min(now + timedelta(days=days), max_limit)
        return {
            "device_token": dt.device_token,
            "expires_at": dt.expires_at.isoformat(),
            "device_name": dt.device_name
        }

def revoke_device_token(token: str):
    """Revokes a specific device token."""
    if not token:
        return
    with get_db_session() as session:
        session.execute(delete(DeviceToken).where(DeviceToken.device_token == token))

def revoke_user_device_tokens(user_id: int):
    """Revokes all device tokens for a user (called on password change, logout, or account delete)."""
    with get_db_session() as session:
        session.execute(delete(DeviceToken).where(DeviceToken.user_id == user_id))

def change_user_password(user_id: int, old_password: str, new_password: str) -> None:
    """
    Requirement 9: Invalidate sessions on password change.
    Verifies old password, hashes new password with argon2, and logs safe audit entry.
    Also revokes all mobile companion device tokens for safety.
    """
    if len(new_password) < 8:
        raise ValueError("New password must be at least 8 characters long.")
    with get_db_session() as session:
        user = session.scalar(select(User).where(User.id == user_id))
        if not user:
            raise ValueError("User not found.")
        if not verify_password(user.password_hash, old_password):
            raise ValueError("Current password is incorrect.")

        user.password_hash = hash_password(new_password)
        # Invalidate all active sessions across all devices
        session.execute(delete(UserSession).where(UserSession.user_id == user_id))
        # Revoke all device tokens
        session.execute(delete(DeviceToken).where(DeviceToken.user_id == user_id))
        log_audit(user_id, "PASSWORD_CHANGED", "Password successfully updated; all sessions and device tokens invalidated.", session=session)

def delete_user_account(user_id: int):
    """
    Requirement 7 & 8: 'Delete my account and all my data'.
    Permanently erases all records for that user, including sessions, device tokens,
    settings, messages, tasks, facts, pending actions, and audit entries.
    """
    with get_db_session() as session:
        user = session.scalar(select(User).where(User.id == user_id))
        if user:
            clean_email = user.email
            session.execute(delete(LoginAttempt).where(LoginAttempt.identifier == clean_email))

        session.execute(delete(UserSession).where(UserSession.user_id == user_id))
        session.execute(delete(DeviceToken).where(DeviceToken.user_id == user_id))
        session.execute(delete(UserSetting).where(UserSetting.user_id == user_id))
        session.execute(delete(Message).where(Message.user_id == user_id))
        session.execute(delete(Task).where(Task.user_id == user_id))
        session.execute(delete(Fact).where(Fact.user_id == user_id))
        session.execute(delete(PendingAction).where(PendingAction.user_id == user_id))
        session.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
        session.execute(delete(User).where(User.id == user_id))

def export_user_data(user_id: int) -> dict:
    """
    Requirement 7: 'Download my data' (JSON export of the user's own
    messages, facts, tasks, and settings). Decrypts messages and facts.
    """
    with get_db_session() as session:
        user = session.scalar(select(User).where(User.id == user_id))
        if not user:
            raise ValueError("User not found.")

        settings = get_all_settings(user_id)
        messages = get_all_messages(user_id)
        facts = get_all_facts(user_id)
        tasks = get_all_tasks(user_id)

        log_audit(user_id, "DATA_EXPORTED", "User requested full personal data archive download.", session=session)

        return {
            "app": "SINBHA",
            "export_version": "1.0",
            "exported_at": utc_now().isoformat(),
            "user": {
                "id": user.id,
                "email": user.email,
                "timezone": user.timezone,
                "is_admin": bool(user.is_admin),
                "created_at": user.created_at.isoformat() if user.created_at else None,
            },
            "settings": settings,
            "messages": messages,
            "facts": facts,
            "tasks": tasks
        }

def get_user_today_message_count(user_id: int) -> int:
    """Returns number of chat messages sent by this user today in UTC."""
    today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    with get_db_session() as session:
        return session.scalar(
            select(func.count(Message.id)).where(
                Message.user_id == user_id,
                Message.role == "user",
                Message.timestamp >= today_start
            )
        ) or 0

def get_global_today_message_count() -> int:
    """Returns total chat messages sent by all users today in UTC (cost cap kill switch)."""
    today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    with get_db_session() as session:
        return session.scalar(
            select(func.count(Message.id)).where(
                Message.role == "user",
                Message.timestamp >= today_start
            )
        ) or 0

# ----------------- Chat Messages Operations (Per-User, Encrypted at Rest) -----------------

def save_message(user_id: int, role: str, content: str):
    """
    Saves a conversation message for the user.
    Requirement 8: Sensitive message content is encrypted at rest using Fernet.
    """
    encrypted_content = encrypt_text(content)
    with get_db_session() as session:
        msg = Message(user_id=user_id, role=role, content=encrypted_content, timestamp=utc_now())
        session.add(msg)

def get_recent_messages(user_id: int, limit: int = 20):
    """Retrieves recent conversation messages with decrypted content."""
    with get_db_session() as session:
        query = (
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(desc(Message.timestamp), desc(Message.id))
            .limit(limit)
        )
        msgs = session.scalars(query).all()
        # Return in chronological order
        return [
            {
                "id": m.id,
                "role": m.role,
                "content": decrypt_text(m.content),
                "timestamp": m.timestamp.isoformat() if m.timestamp else ""
            }
            for m in reversed(msgs)
        ]

def get_all_messages(user_id: int):
    """Returns all chat messages for this user with decrypted content."""
    with get_db_session() as session:
        query = (
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.timestamp.asc(), Message.id.asc())
        )
        msgs = session.scalars(query).all()
        return [
            {
                "id": m.id,
                "role": m.role,
                "content": decrypt_text(m.content),
                "timestamp": m.timestamp.isoformat() if m.timestamp else ""
            }
            for m in msgs
        ]

# ----------------- Facts & Memory Operations (Per-User, Encrypted at Rest) -----------------

def get_all_facts(user_id: int):
    """Returns all persistent facts for this user with decrypted text."""
    with get_db_session() as session:
        query = select(Fact).where(Fact.user_id == user_id).order_by(Fact.id.desc())
        facts = session.scalars(query).all()
        return [
            {
                "id": f.id,
                "fact": decrypt_text(f.fact),
                "category": f.category,
                "created_at": f.created_at.isoformat() if f.created_at else ""
            }
            for f in facts
        ]

def add_fact(user_id: int, fact_text: str, category: str = "general") -> int:
    """Adds a new fact to continuous memory, encrypted at rest."""
    clean = fact_text.strip()
    if not clean:
        return -1
    with get_db_session() as session:
        # Check duplicate against decrypted user facts
        user_facts = session.scalars(select(Fact).where(Fact.user_id == user_id)).all()
        for uf in user_facts:
            if decrypt_text(uf.fact).strip().lower() == clean.lower():
                return uf.id

        encrypted = encrypt_text(clean)
        fact = Fact(user_id=user_id, fact=encrypted, category=category, created_at=utc_now())
        session.add(fact)
        session.flush()
        # Requirement 6: Never log raw fact text in audit log
        log_audit(user_id, "FACT_SAVED", f"Recorded new memory fact #{fact.id}", session=session)
        return fact.id

def update_fact(user_id: int, fact_id: int, new_text: str) -> bool:
    """Updates an existing fact with encrypted text."""
    clean = new_text.strip()
    if not clean:
        return False
    with get_db_session() as session:
        fact = session.scalar(
            select(Fact).where(Fact.id == fact_id, Fact.user_id == user_id)
        )
        if not fact:
            return False
        fact.fact = encrypt_text(clean)
        log_audit(user_id, "FACT_UPDATED", f"Modified memory fact #{fact_id}", session=session)
        return True

def delete_fact(user_id: int, fact_id: int) -> bool:
    """Deletes a fact from the user's memory."""
    with get_db_session() as session:
        fact = session.scalar(
            select(Fact).where(Fact.id == fact_id, Fact.user_id == user_id)
        )
        if not fact:
            return False
        session.delete(fact)
        log_audit(user_id, "FACT_DELETED", f"Deleted memory fact #{fact_id}", session=session)
        return True

def update_or_add_fact(user_id: int, fact_text: str, category: str = "general") -> dict:
    """Intelligently updates an existing related fact or inserts a new encrypted one."""
    clean = fact_text.strip()
    if not clean:
        return {"action": "none"}

    with get_db_session() as session:
        user_facts = session.scalars(select(Fact).where(Fact.user_id == user_id)).all()

        # Exact match
        for uf in user_facts:
            decrypted = decrypt_text(uf.fact)
            if decrypted.strip().lower() == clean.lower():
                return {"action": "none", "fact_id": uf.id, "fact": decrypted}

        # Check for key phrases like "name is", "lives in"
        attr_patterns = [
            (r"\bname\s+is\s+([A-Za-z]+)", "name is"),
            (r"\blives?\s+in\s+([A-Za-z\s]+)", "lives in"),
            (r"\bworks?\s+at\s+([A-Za-z\s]+)", "works at"),
            (r"\bpet\s+is\s+([A-Za-z\s]+)", "pet is"),
        ]
        import re
        for pat, key in attr_patterns:
            m = re.search(pat, clean, re.IGNORECASE)
            if m:
                for uf in user_facts:
                    decrypted = decrypt_text(uf.fact)
                    if key in decrypted.lower():
                        old_text = decrypted
                        uf.fact = encrypt_text(clean)
                        log_audit(user_id, "FACT_UPDATED", f"Updated attribute #{uf.id}", session=session)
                        return {"action": "updated", "fact_id": uf.id, "fact": clean, "old_fact": old_text}

        # Add as new
        fact = Fact(user_id=user_id, fact=encrypt_text(clean), category=category, created_at=utc_now())
        session.add(fact)
        session.flush()
        log_audit(user_id, "FACT_SAVED", f"Recorded new memory fact #{fact.id}", session=session)
        return {"action": "added", "fact_id": fact.id, "fact": clean}


# ----------------- Pending Actions & Proposals (Per-User) -----------------

def set_pending_action(user_id: int, action_type: str, target_id: int = None, target_text: str = "", details: str = ""):
    """Sets a pending two-step action requiring user confirmation."""
    with get_db_session() as session:
        session.execute(delete(PendingAction).where(PendingAction.user_id == user_id))
        pa = PendingAction(
            user_id=user_id,
            action_type=action_type,
            target_id=target_id,
            target_text=target_text,
            details=details,
            created_at=utc_now()
        )
        session.add(pa)

def get_pending_action(user_id: int) -> Optional[dict]:
    """Retrieves the active pending action for this user."""
    with get_db_session() as session:
        pa = session.scalar(
            select(PendingAction).where(PendingAction.user_id == user_id).order_by(PendingAction.id.desc())
        )
        if not pa:
            return None
        return {
            "id": pa.id,
            "action_type": pa.action_type,
            "target_id": pa.target_id,
            "target_text": pa.target_text,
            "details": pa.details,
            "created_at": pa.created_at.isoformat() if pa.created_at else ""
        }

def clear_pending_action(user_id: int):
    """Clears pending action for this user."""
    with get_db_session() as session:
        session.execute(delete(PendingAction).where(PendingAction.user_id == user_id))

def set_pending_proposal(
    user_id: int,
    title: str,
    due_date: str = None,
    due_time: str = None,
    notes: str = None,
    suggested_reminders: list = None,
    due_datetime: str = None,
    **kwargs
):
    """Sets a pending task creation proposal."""
    payload = {
        "title": title,
        "due_date": due_date,
        "due_time": due_time,
        "due_datetime": due_datetime,
        "notes": notes,
        "suggested_reminders": suggested_reminders or []
    }
    set_pending_action(user_id, "create_task", target_text=title, details=json.dumps(payload))
    pa = get_pending_proposal(user_id)
    return pa.get("proposal_id", -1) if pa else -1

def get_pending_proposal(user_id: int) -> dict | None:
    """Retrieves a pending task proposal."""
    pa = get_pending_action(user_id)
    if not pa or pa["action_type"] != "create_task":
        return None
    try:
        data = json.loads(pa["details"])
        data["proposal_id"] = pa["id"]
        return data
    except Exception:
        return None

def cancel_pending_proposal(user_id: int, reason: str = "User cancelled") -> bool:
    """Cancels a pending task proposal."""
    pa = get_pending_proposal(user_id)
    if not pa:
        return False
    clear_pending_action(user_id)
    log_audit(user_id, "TASK_PROPOSAL_CANCELLED", f"Proposal '{pa.get('title')}' cancelled: {reason}")
    return True

def confirm_pending_proposal(user_id: int, chosen_reminders: list = None) -> dict | None:
    """Confirms pending task proposal and creates the task."""
    pa = get_pending_proposal(user_id)
    if not pa:
        return None

    reminders = chosen_reminders if chosen_reminders is not None else pa.get("suggested_reminders", [])
    task_id = create_task(
        user_id=user_id,
        title=pa["title"],
        due_date=pa.get("due_date"),
        due_time=pa.get("due_time"),
        notes=pa.get("notes"),
        chosen_reminders=reminders
    )
    clear_pending_action(user_id)
    return get_task_by_id(user_id, task_id)

def set_pending_task_action(user_id: int, action_type: str, task_id: int, task_title: str) -> int:
    """Sets a pending task mutation (complete or delete)."""
    set_pending_action(user_id, action_type, target_id=task_id, target_text=task_title)
    pa = get_pending_action(user_id)
    return pa["id"] if pa else -1

def get_pending_task_action(user_id: int) -> dict | None:
    """Retrieves a pending task mutation."""
    pa = get_pending_action(user_id)
    if not pa or pa["action_type"] not in ("task_complete", "task_delete"):
        return None
    return {
        "id": pa["id"],
        "action_type": pa["action_type"],
        "task_id": pa["target_id"],
        "task_title": pa["target_text"]
    }

def cancel_pending_task_action(user_id: int, reason: str = "User cancelled") -> bool:
    """Cancels a pending task mutation."""
    pa = get_pending_task_action(user_id)
    if not pa:
        return False
    clear_pending_action(user_id)
    log_audit(user_id, "TASK_ACTION_CANCELLED", f"Action {pa['action_type']} for #{pa['task_id']} cancelled: {reason}")
    return True

def confirm_pending_task_action(user_id: int) -> dict | None:
    """Executes a confirmed task mutation."""
    pa = get_pending_task_action(user_id)
    if not pa:
        return None
    task_id = pa["task_id"]
    action_type = pa["action_type"]

    if action_type == "task_complete":
        update_task_status(user_id, task_id, "completed")
        res = {"action": "completed", "task_id": task_id, "task_title": pa["task_title"]}
    elif action_type == "task_delete":
        delete_task(user_id, task_id)
        res = {"action": "deleted", "task_id": task_id, "task_title": pa["task_title"]}
    else:
        res = None

    clear_pending_action(user_id)
    return res

# ----------------- Tasks & Reminders Operations (Per-User, Step 6B & 10) -----------------

def create_task(
    user_id: int,
    title: str,
    due_date: str = None,
    due_time: str = None,
    notes: str = None,
    chosen_reminders: list = None,
    due_datetime_utc: datetime = None
) -> int:
    """Creates a task with UTC timestamps and chosen reminders."""
    clean_title = title.strip()
    rem_json = json.dumps(chosen_reminders) if chosen_reminders else None
    with get_db_session() as session:
        task = Task(
            user_id=user_id,
            title=clean_title,
            due_date=due_date,
            due_time=due_time,
            due_datetime_utc=due_datetime_utc,
            notes=notes,
            status="pending",
            reminders_json=rem_json,
            fired_reminders_json="[]",
            created_at=utc_now()
        )
        session.add(task)
        session.flush()
        task_id = task.id
        log_audit(user_id, "TASK_CREATED", f"Task #{task_id} created: '{clean_title}' (Due: {due_date} {due_time or ''})", session=session)
        return task_id

def task_sort_key(t):
    """Helper to sort tasks: Overdue first, then by date, then no-date."""
    due = t.get("due_date")
    time_str = t.get("due_time") or "23:59"
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not due:
        return (2, "9999-99-99", "99:99")
    if due < today_str:
        return (0, due, time_str)
    return (1, due, time_str)

def get_all_tasks(user_id: int) -> list:
    """Retrieves all tasks for this user, sorted chronologically."""
    with get_db_session() as session:
        query = select(Task).where(Task.user_id == user_id)
        tasks = session.scalars(query).all()
        task_list = []
        for t in tasks:
            task_list.append({
                "id": t.id,
                "title": t.title,
                "due_date": t.due_date,
                "due_time": t.due_time,
                "due_datetime_utc": t.due_datetime_utc.isoformat() if t.due_datetime_utc else None,
                "notes": t.notes,
                "status": t.status,
                "reminders": json.loads(t.reminders_json) if t.reminders_json else [],
                "fired_reminders": json.loads(t.fired_reminders_json) if t.fired_reminders_json else [],
                "snoozed_until": t.snoozed_until.isoformat() if t.snoozed_until else None,
                "created_at": t.created_at.isoformat() if t.created_at else ""
            })
        task_list.sort(key=task_sort_key)
        return task_list

def get_task_by_id(user_id: int, task_id: int) -> dict | None:
    """Retrieves a single task by ID strictly for the logged-in user."""
    with get_db_session() as session:
        t = session.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))
        if not t:
            return None
        return {
            "id": t.id,
            "title": t.title,
            "due_date": t.due_date,
            "due_time": t.due_time,
            "due_datetime_utc": t.due_datetime_utc.isoformat() if t.due_datetime_utc else None,
            "notes": t.notes,
            "status": t.status,
            "reminders": json.loads(t.reminders_json) if t.reminders_json else [],
            "fired_reminders": json.loads(t.fired_reminders_json) if t.fired_reminders_json else [],
            "snoozed_until": t.snoozed_until.isoformat() if t.snoozed_until else None,
            "created_at": t.created_at.isoformat() if t.created_at else ""
        }

def update_task_status(user_id: int, task_id: int, new_status: str) -> bool:
    """Updates a task status (pending or completed)."""
    with get_db_session() as session:
        t = session.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))
        if not t:
            return False
        old_status = t.status
        t.status = new_status
        log_audit(user_id, "TASK_STATUS_UPDATED", f"Task #{task_id} status changed from '{old_status}' to '{new_status}'", session=session)
        return True

def delete_task(user_id: int, task_id: int) -> bool:
    """Deletes a task permanently."""
    with get_db_session() as session:
        t = session.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))
        if not t:
            return False
        title = t.title
        session.delete(t)
        log_audit(user_id, "TASK_DELETED", f"Task #{task_id} deleted: '{title}'", session=session)
        return True

def get_pending_tasks_count(user_id: int) -> int:
    """Returns number of pending tasks for this user."""
    with get_db_session() as session:
        return session.scalar(
            select(func.count(Task.id)).where(Task.user_id == user_id, Task.status == "pending")
        ) or 0

# ----------------- Settings & User State Operations (Per-User) -----------------

def get_setting(user_id: int, key: str, default: str = None) -> str:
    """Gets a user setting."""
    with get_db_session() as session:
        st = session.scalar(
            select(UserSetting).where(UserSetting.user_id == user_id, UserSetting.key == key)
        )
        return st.value if st else default

def set_setting(user_id: int, key: str, value: str) -> None:
    """Sets a user setting."""
    with get_db_session() as session:
        st = session.scalar(
            select(UserSetting).where(UserSetting.user_id == user_id, UserSetting.key == key)
        )
        if st:
            st.value = str(value)
            st.updated_at = utc_now()
        else:
            st = UserSetting(user_id=user_id, key=key, value=str(value), updated_at=utc_now())
            session.add(st)

def get_all_settings(user_id: int) -> dict:
    """Retrieves all settings for the user."""
    defaults = {
        "persistence": "normal",
        "quiet_hours_enabled": "true",
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00",
        "country": "US",
        "timezone": "UTC"
    }
    with get_db_session() as session:
        settings = session.scalars(select(UserSetting).where(UserSetting.user_id == user_id)).all()
        result = dict(defaults)
        for s in settings:
            result[s.key] = s.value
        return result

def set_emergency_stopped(user_id: int, stopped: bool) -> None:
    """Sets emergency STOP state per user."""
    with get_db_session() as session:
        user = session.scalar(select(User).where(User.id == user_id))
        if user:
            user.emergency_stopped = 1 if stopped else 0
            log_audit(user_id, "EMERGENCY_STOP" if stopped else "EMERGENCY_RESUME",
                      "Emergency stop activated" if stopped else "Chat and reminders resumed",
                      session=session)

def get_emergency_stopped(user_id: int) -> bool:
    """Checks if emergency STOP is active for this user."""
    with get_db_session() as session:
        user = session.scalar(select(User).where(User.id == user_id))
        return bool(user.emergency_stopped) if user else False

# ----------------- Reminders & Bird Flight Controller (Per-User, Step 6B & 10) -----------------

def reminder_sort_key(item):
    """Sorts reminders chronologically so the earliest due reminder arrives first."""
    rem_time = item.get("reminder_time")
    if rem_time:
        return (0, rem_time)
    due_date = item["task"].get("due_date")
    due_time = item["task"].get("due_time") or "23:59"
    if due_date:
        return (1, f"{due_date} {due_time}")
    return (2, "9999-99-99 99:99")

def check_due_reminders(user_id: int, now_dt: datetime = None) -> list:
    """
    Checks if any explicit reminder or persistent task check-in is due for this user.
    Handles quiet hours, snoozes, and returns reminders in chronological order.
    """
    if get_emergency_stopped(user_id):
        return []

    settings = get_all_settings(user_id)
    now = now_dt or utc_now()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    current_time_str = now.strftime("%H:%M")

    # Quiet hours check
    is_quiet_hours = False
    if settings.get("quiet_hours_enabled") == "true":
        start_q = settings.get("quiet_hours_start", "22:00")
        end_q = settings.get("quiet_hours_end", "08:00")
        if start_q > end_q:
            if current_time_str >= start_q or current_time_str < end_q:
                is_quiet_hours = True
        else:
            if start_q <= current_time_str < end_q:
                is_quiet_hours = True

    pending_tasks = [t for t in get_all_tasks(user_id) if t["status"] == "pending"]
    due_items = []

    for t in pending_tasks:
        # Check snooze
        snooze_str = t.get("snoozed_until")
        if snooze_str:
            try:
                sn_dt = datetime.fromisoformat(snooze_str)
                if sn_dt.tzinfo is None:
                    sn_dt = sn_dt.replace(tzinfo=timezone.utc)
                if now < sn_dt:
                    continue
            except Exception:
                pass

        # 1. Check explicit scheduled reminders
        reminders = t.get("reminders") or []
        fired_ids = set(t.get("fired_reminders") or [])
        matched_explicit = False

        for r in reminders:
            r_id = r.get("id")
            r_time = r.get("time")
            if not r_id or r_id in fired_ids or not r_time:
                continue

            if r_time <= now_str:
                due_items.append({
                    "task": t,
                    "reminder_id": r_id,
                    "is_explicit": True,
                    "reminder_label": r.get("label", "Scheduled Reminder"),
                    "reminder_time": r_time
                })
                matched_explicit = True
                break

        if matched_explicit:
            continue

        # 2. Quiet hours suppresses non-explicit bird visits
        if is_quiet_hours:
            continue

        # 3. Persistent visits for tasks with due dates
        due_d = t.get("due_date")
        due_t = t.get("due_time")
        if due_d:
            due_full = f"{due_d} {due_t if due_t else '09:00'}"
            if due_full <= now_str:
                due_items.append({
                    "task": t,
                    "reminder_id": None,
                    "is_explicit": False,
                    "reminder_label": "Overdue Check-in",
                    "reminder_time": due_full
                })

    due_items.sort(key=reminder_sort_key)
    return due_items

def mark_reminder_fired(user_id: int, task_id: int, reminder_id: str = None) -> bool:
    """Marks an explicit reminder as fired in database."""
    with get_db_session() as session:
        t = session.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))
        if not t:
            return False

        fired = json.loads(t.fired_reminders_json) if t.fired_reminders_json else []
        if reminder_id and reminder_id not in fired:
            fired.append(reminder_id)
            t.fired_reminders_json = json.dumps(fired)

        log_audit(user_id, "REMINDER_FIRED", f"Reminder {reminder_id or 'default'} fired for task #{task_id}")
        return True

def snooze_task(user_id: int, task_id: int, minutes: int) -> bool:
    """Snoozes a task by the given number of minutes."""
    snooze_until = utc_now() + timedelta(minutes=minutes)
    with get_db_session() as session:
        t = session.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))
        if not t:
            return False
        t.snoozed_until = snooze_until
        log_audit(user_id, "REMINDER_SNOOZED", f"Task #{task_id} snoozed for {minutes}m until {snooze_until.isoformat()}", session=session)
        return True

# ----------------- Audit Logs & Purge Operations (Per-User) -----------------

def log_audit(user_id: Optional[int], action: str, details: str = "", session: Optional[OrmSession] = None):
    """Logs an audit record."""
    try:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            details=details,
            timestamp=utc_now()
        )
        if session is not None:
            session.add(entry)
        else:
            with get_db_session() as sess:
                sess.add(entry)
    except Exception as e:
        print(f"[Audit Error] {e}")

def get_audit_logs(user_id: int, limit: int = 50):
    """Retrieves audit entries for the user."""
    with get_db_session() as session:
        query = (
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        logs = session.scalars(query).all()
        return [
            {
                "id": l.id,
                "action": l.action,
                "details": l.details,
                "timestamp": l.timestamp.isoformat() if l.timestamp else ""
            }
            for l in logs
        ]

def purge_all_data(user_id: int):
    """Clears messages, tasks, and facts for this user, keeping the user account."""
    with get_db_session() as session:
        session.execute(delete(Message).where(Message.user_id == user_id))
        session.execute(delete(Task).where(Task.user_id == user_id))
        session.execute(delete(Fact).where(Fact.user_id == user_id))
        session.execute(delete(PendingAction).where(PendingAction.user_id == user_id))
        log_audit(user_id, "USER_DATA_PURGED", "User cleared all chat history, memory facts, and tasks.", session=session)

# ----------------- Step 16 & 16b: Device Pairing & Management -----------------

def _device_to_dict(dev: Device) -> dict:
    capabilities = {"note": True, "open_link": True, "ring": True, "sync": True}
    if dev.capabilities_json:
        try:
            capabilities = json.loads(dev.capabilities_json)
        except Exception:
            pass

    expires_in_seconds = 0
    if dev.pairing_expires_at:
        now = utc_now()
        exp = dev.pairing_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        diff = int((exp - now).total_seconds())
        expires_in_seconds = max(0, diff)

    attempts = getattr(dev, "pairing_attempts", 0) or 0
    is_locked = attempts >= 5

    return {
        "id": dev.id,
        "device_id": dev.device_id,
        "name": dev.name,
        "platform": dev.platform,
        "status": dev.status,
        "permission_level": dev.permission_level,
        "capabilities": capabilities,
        "pairing_code": dev.pairing_code if (dev.status == "pending" and expires_in_seconds > 0 and not is_locked) else None,
        "expires_in_seconds": expires_in_seconds if dev.status == "pending" and not is_locked else 0,
        "pairing_attempts": attempts,
        "is_locked": is_locked,
        "created_at": dev.created_at.isoformat() if dev.created_at else "",
        "last_seen_at": dev.last_seen_at.isoformat() if dev.last_seen_at else "",
    }

def verify_user_password(user_id: int, password: str) -> bool:
    """Verifies plain password against user's argon2 hash."""
    with get_db_session() as session:
        user = session.scalar(select(User).where(User.id == user_id))
        if not user:
            return False
        return verify_password(user.password_hash, password)

def create_or_register_device(
    user_id: int,
    device_id: str,
    name: str = "Unknown Device",
    platform: str = "web",
    is_signup: bool = False,
    password: Optional[str] = None,
) -> dict:
    """
    Registers a device for the user.
    Step 16b Rules:
    - New accounts at signup (is_signup=True or user created < 120s ago) may trust their first device automatically.
    - For an account that already exists:
      the first device must NOT become trusted automatically.
      It requires re-entering the password to become trusted.
    - Subsequent new devices (trusted_count > 0) are marked 'pending' and given a 6-digit one-time code expiring in 5 min.
    - If device already exists and belongs to this user: updates last_seen_at, name, platform.
    """
    with get_db_session() as session:
        user = session.scalar(select(User).where(User.id == user_id))
        if not user:
            raise ValueError("User not found.")

        dev = session.scalar(select(Device).where(Device.device_id == device_id))
        if dev:
            if dev.user_id != user_id:
                raise ValueError("Device is already registered to another user account.")
            dev.last_seen_at = utc_now()
            if name and name != "Unknown Device":
                dev.name = name
            if platform:
                dev.platform = platform

            # If pending and user provides password for existing account verification
            if dev.status == "pending" and password:
                if verify_password(user.password_hash, password):
                    dev.status = "trusted"
                    dev.pairing_code = None
                    dev.pairing_expires_at = None
                    dev.pairing_attempts = 0
                    log_audit(
                        user_id,
                        "DEVICE_REGISTERED_TRUSTED",
                        f"Device '{dev.name}' ({device_id}) verified with password and trusted.",
                        session=session
                    )
                else:
                    raise ValueError("Incorrect password. Re-entering your password is required to trust this device on an existing account.")

            # If still pending and code expired, auto-refresh code if not locked
            elif dev.status == "pending" and dev.pairing_expires_at and (getattr(dev, "pairing_attempts", 0) or 0) < 5:
                now = utc_now()
                exp = dev.pairing_expires_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if now > exp:
                    dev.pairing_code = f"{secrets.randbelow(900000) + 100000}"
                    dev.pairing_expires_at = now + timedelta(minutes=5)

            session.flush()
            return _device_to_dict(dev)

        # New device registration
        trusted_count = session.scalar(
            select(func.count(Device.id))
            .where(and_(Device.user_id == user_id, Device.status == "trusted"))
        ) or 0

        now = utc_now()
        user_created = user.created_at
        if user_created and user_created.tzinfo is None:
            user_created = user_created.replace(tzinfo=timezone.utc)
        is_recent_signup = is_signup or (user_created and (now - user_created).total_seconds() < 120)

        if trusted_count == 0:
            if is_recent_signup:
                # New account at signup: trust first device
                status = "trusted"
                pairing_code = None
                pairing_expires_at = None
                log_audit(
                    user_id,
                    "DEVICE_REGISTERED_TRUSTED",
                    f"First device on new signup '{name}' ({device_id}) registered as trusted.",
                    session=session
                )
            else:
                # Account already exists! Must NOT become trusted automatically.
                # Requires re-entering the password.
                if password:
                    if verify_password(user.password_hash, password):
                        status = "trusted"
                        pairing_code = None
                        pairing_expires_at = None
                        log_audit(
                            user_id,
                            "DEVICE_REGISTERED_TRUSTED",
                            f"First device for existing account '{name}' ({device_id}) verified with password and trusted.",
                            session=session
                        )
                    else:
                        raise ValueError("Incorrect password. Re-entering your password is required to trust this device on an existing account.")
                else:
                    status = "pending"
                    pairing_code = f"{secrets.randbelow(900000) + 100000}"
                    pairing_expires_at = now + timedelta(minutes=5)
                    log_audit(
                        user_id,
                        "DEVICE_REGISTERED_PENDING",
                        f"First device for existing account '{name}' ({device_id}) pending password verification.",
                        session=session
                    )
        else:
            status = "pending"
            pairing_code = f"{secrets.randbelow(900000) + 100000}"
            pairing_expires_at = now + timedelta(minutes=5)
            log_audit(
                user_id,
                "DEVICE_REGISTERED_PENDING",
                f"New device '{name}' ({device_id}) registered pending pairing approval.",
                session=session
            )

        new_dev = Device(
            user_id=user_id,
            device_id=device_id,
            name=name,
            platform=platform,
            status=status,
            permission_level=1,
            capabilities_json=json.dumps({"note": True, "open_link": True, "ring": True, "sync": True}),
            pairing_code=pairing_code,
            pairing_expires_at=pairing_expires_at,
            pairing_attempts=0,
            created_at=now,
            last_seen_at=now,
        )
        session.add(new_dev)
        session.flush()
        return _device_to_dict(new_dev)

def get_user_devices(user_id: int) -> List[dict]:
    """Lists all devices belonging to the user."""
    with get_db_session() as session:
        devices = session.scalars(
            select(Device).where(Device.user_id == user_id).order_by(Device.created_at.asc())
        ).all()
        return [_device_to_dict(d) for d in devices]

def get_device_by_id(user_id: int, device_id: str) -> Optional[dict]:
    """Retrieves a single device by device_id belonging to user_id."""
    with get_db_session() as session:
        dev = session.scalar(
            select(Device).where(and_(Device.user_id == user_id, Device.device_id == device_id))
        )
        return _device_to_dict(dev) if dev else None

def approve_device_pairing(user_id: int, code: str, approver_device_id: Optional[str] = None) -> dict:
    """
    Approves a pending device pairing using its 6-digit one-time code.
    Step 16b Rules:
    - Pairing approval always requires typing the 6-digit code.
    - Locks the code after 5 wrong attempts.
    """
    clean_code = str(code).strip()
    with get_db_session() as session:
        if approver_device_id:
            approver = session.scalar(
                select(Device).where(and_(Device.user_id == user_id, Device.device_id == approver_device_id))
            )
            if not approver or approver.status != "trusted":
                return {"success": False, "error": "APPROVER_NOT_TRUSTED", "message": "Approver device is not trusted."}

        # Find pending device(s) for this user
        pending_devices = session.scalars(
            select(Device).where(and_(Device.user_id == user_id, Device.status == "pending"))
        ).all()

        if not pending_devices:
            return {"success": False, "error": "NO_PENDING_DEVICE", "message": "No pending device found awaiting pairing approval."}

        # Check if code matches any pending device
        matched_target = None
        for dev in pending_devices:
            if dev.pairing_code and dev.pairing_code == clean_code:
                matched_target = dev
                break

        if not matched_target:
            # Code mismatch: increment failed attempts on pending devices
            for dev in pending_devices:
                dev.pairing_attempts = (getattr(dev, "pairing_attempts", 0) or 0) + 1
                if dev.pairing_attempts >= 5:
                    dev.pairing_code = None
                    dev.pairing_expires_at = None
                    log_audit(
                        user_id,
                        "DEVICE_PAIRING_LOCKED",
                        f"Pairing code locked after 5 failed attempts for device '{dev.name}' ({dev.device_id}).",
                        session=session
                    )
            session.flush()

            locked_devs = [d for d in pending_devices if d.pairing_attempts >= 5]
            if locked_devs:
                return {
                    "success": False,
                    "error": "CODE_LOCKED",
                    "message": "Too many failed attempts. Pairing code is locked. Please generate a new code on the device."
                }
            remaining = 5 - pending_devices[0].pairing_attempts
            return {
                "success": False,
                "error": "INVALID_CODE",
                "message": f"Invalid pairing code. {remaining} attempt(s) remaining before lock."
            }

        # Check if already locked
        if (getattr(matched_target, "pairing_attempts", 0) or 0) >= 5:
            return {
                "success": False,
                "error": "CODE_LOCKED",
                "message": "Pairing code is locked after 5 failed attempts. Please generate a new code on the device."
            }

        # Check expiry
        if matched_target.pairing_expires_at:
            now = utc_now()
            exp = matched_target.pairing_expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now > exp:
                return {
                    "success": False,
                    "error": "EXPIRED",
                    "message": "Pairing code expired (5-minute limit). Please refresh code on the new device."
                }

        # Approval succeeds
        matched_target.status = "trusted"
        matched_target.pairing_code = None
        matched_target.pairing_expires_at = None
        matched_target.pairing_attempts = 0
        matched_target.last_seen_at = utc_now()
        log_audit(
            user_id,
            "DEVICE_PAIRING_APPROVED",
            f"Device '{matched_target.name}' ({matched_target.device_id}) approved and trusted.",
            session=session
        )
        return {
            "success": True,
            "message": f"Device '{matched_target.name}' is now paired and trusted! 🌸",
            "device": _device_to_dict(matched_target)
        }

def regenerate_pairing_code(user_id: int, device_id: str) -> dict:
    """Regenerates a fresh 5-minute pairing code for a pending device and resets failed attempts."""
    with get_db_session() as session:
        dev = session.scalar(
            select(Device).where(and_(Device.user_id == user_id, Device.device_id == device_id))
        )
        if not dev:
            raise ValueError("Device not found.")
        if dev.status != "pending":
            return _device_to_dict(dev)

        now = utc_now()
        dev.pairing_code = f"{secrets.randbelow(900000) + 100000}"
        dev.pairing_expires_at = now + timedelta(minutes=5)
        dev.pairing_attempts = 0
        dev.last_seen_at = now
        session.flush()
        return _device_to_dict(dev)

def rename_device(user_id: int, device_id: str, new_name: str) -> dict:
    """Renames an existing device."""
    with get_db_session() as session:
        dev = session.scalar(
            select(Device).where(and_(Device.user_id == user_id, Device.device_id == device_id))
        )
        if not dev:
            raise ValueError("Device not found.")
        old_name = dev.name
        dev.name = new_name.strip()[:128]
        log_audit(
            user_id,
            "DEVICE_RENAMED",
            f"Renamed device '{old_name}' -> '{dev.name}' ({device_id})",
            session=session
        )
        return _device_to_dict(dev)

def update_device_permissions(
    user_id: int,
    device_id: str,
    permission_level: Optional[int] = None,
    capabilities: Optional[dict] = None,
    password: Optional[str] = None,
) -> dict:
    """
    Updates permission level (0-4) and capabilities for a device.
    Step 16b Rule 4: Raising permission to Level 2 or higher, or enabling 'open link',
    strictly requires re-entering the account password.
    """
    with get_db_session() as session:
        user = session.scalar(select(User).where(User.id == user_id))
        if not user:
            raise ValueError("User not found.")

        dev = session.scalar(
            select(Device).where(and_(Device.user_id == user_id, Device.device_id == device_id))
        )
        if not dev:
            raise ValueError("Device not found.")

        # Check if raising permission level to >= 2
        is_raising_level = (
            permission_level is not None
            and int(permission_level) >= 2
            and int(permission_level) > dev.permission_level
        )

        # Check if enabling "open_link"
        current_caps = json.loads(dev.capabilities_json) if dev.capabilities_json else {}
        is_enabling_open_link = (
            capabilities is not None
            and capabilities.get("open_link") is True
            and not current_caps.get("open_link", False)
        )

        if is_raising_level or is_enabling_open_link:
            if not password or not verify_password(user.password_hash, password):
                raise ValueError("PASSWORD_REQUIRED: Re-entering your password is required to raise permission to Level 2+ or enable open link.")

        if permission_level is not None:
            dev.permission_level = max(0, min(4, int(permission_level)))
        if capabilities is not None:
            dev.capabilities_json = json.dumps(capabilities)

        log_audit(
            user_id,
            "DEVICE_PERMISSIONS_UPDATED",
            f"Updated permissions for '{dev.name}' ({device_id}): Level {dev.permission_level}",
            session=session
        )
        return _device_to_dict(dev)

def revoke_device(user_id: int, device_id: str) -> dict:
    """Revokes access for a device immediately."""
    with get_db_session() as session:
        dev = session.scalar(
            select(Device).where(and_(Device.user_id == user_id, Device.device_id == device_id))
        )
        if not dev:
            raise ValueError("Device not found.")
        dev.status = "revoked"
        log_audit(
            user_id,
            "DEVICE_REVOKED",
            f"Device '{dev.name}' ({device_id}) revoked immediately.",
            session=session
        )
        return _device_to_dict(dev)

def disconnect_all_devices(user_id: int) -> int:
    """Revokes access for all devices belonging to the user."""
    with get_db_session() as session:
        result = session.execute(
            update(Device).where(Device.user_id == user_id).values(status="revoked")
        )
        count = result.rowcount
        log_audit(
            user_id,
            "DEVICES_DISCONNECT_ALL",
            f"Disconnected and revoked all {count} devices immediately.",
            session=session
        )
        return count

def update_device_last_seen(device_id: str):
    """Updates device last_seen_at timestamp."""
    try:
        with get_db_session() as session:
            session.execute(
                update(Device).where(Device.device_id == device_id).values(last_seen_at=utc_now())
            )
    except Exception:
        pass


