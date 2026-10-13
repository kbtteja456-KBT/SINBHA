"""
SQLAlchemy 2.0 Declarative Models for SINBHA (Step 10)
Defines models for users, sessions, settings, messages, tasks, facts, audit logs, and pending actions.
All timestamps are stored in UTC.
Indexes on user_id + time columns ensure high-performance per-user isolation.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    relationship,
)

def utc_now() -> datetime:
    """Returns current UTC datetime."""
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Integer, default=0, nullable=False)
    emergency_stopped = Column(Integer, default=0, nullable=False)
    timezone = Column(String(64), default="UTC", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False)

    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("UserSetting", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    facts = relationship("Fact", back_populates="user", cascade="all, delete-orphan")
    pending_actions = relationship("PendingAction", back_populates="user", cascade="all, delete-orphan")
    device_tokens = relationship("DeviceToken", back_populates="user", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")

class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_token = Column(String(128), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="sessions")

class DeviceToken(Base):
    """
    Dedicated token for mobile companion background actions.
    Separated from web sessions, limited strictly to reminder actions
    (fetching upcoming reminders, marking task done, snoozing).
    """
    __tablename__ = "device_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_token = Column(String(128), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_name = Column(String(128), default="Android Companion", nullable=False)
    scope = Column(String(64), default="reminders_only", nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="device_tokens")

class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    identifier = Column(String(255), nullable=False, index=True)
    failed_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_attempt = Column(DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False)

class UserSetting(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key = Column(String(64), nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now, nullable=False)

    user = relationship("User", back_populates="settings")

    __table_args__ = (
        Index("ix_user_settings_user_key", "user_id", "key", unique=True),
    )

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="messages")

    # Compound index on user_id + time column for fast per-user conversation retrieval
    __table_args__ = (
        Index("ix_messages_user_time", "user_id", "timestamp"),
    )

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    title = Column(String(512), nullable=False)
    due_date = Column(String(64), nullable=True)
    due_time = Column(String(64), nullable=True)
    due_datetime_utc = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(32), default="pending", nullable=False)
    reminders_json = Column(Text, nullable=True)
    fired_reminders_json = Column(Text, nullable=True)
    snoozed_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="tasks")

    # Compound indexes on user_id + status, user_id + due_date, user_id + snoozed_until, user_id + due_datetime_utc
    __table_args__ = (
        Index("ix_tasks_user_status", "user_id", "status"),
        Index("ix_tasks_user_due", "user_id", "due_date"),
        Index("ix_tasks_user_snoozed", "user_id", "snoozed_until"),
        Index("ix_tasks_user_due_utc", "user_id", "due_datetime_utc"),
    )

class Fact(Base):
    __tablename__ = "facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    fact = Column(Text, nullable=False)
    category = Column(String(64), default="general", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="facts")

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(64), nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_audit_user_time", "user_id", "timestamp"),
    )

class PendingAction(Base):
    __tablename__ = "pending_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    action_type = Column(String(64), nullable=False)
    target_id = Column(Integer, nullable=True)
    target_text = Column(Text, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="pending_actions")

class Device(Base):
    """
    Step 16: Device pairing and secure command channel.
    Tracks user devices, pairing status, permissions, and capabilities.
    """
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    platform = Column(String(64), default="web", nullable=False)
    status = Column(String(32), default="pending", nullable=False)  # "trusted", "pending", "revoked"
    permission_level = Column(Integer, default=1, nullable=False)  # 0=read-only, 1=safe, 2=confirm, 3=sensitive, 4=never automatic
    capabilities_json = Column(Text, default='{"note": true, "open_link": true, "ring": true, "sync": true}', nullable=False)
    pairing_code = Column(String(16), nullable=True, index=True)
    pairing_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="devices")

    __table_args__ = (
        Index("ix_devices_user_status", "user_id", "status"),
    )

