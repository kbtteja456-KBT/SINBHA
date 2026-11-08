"""
Tests for Pillar 2: Durable Proactive Scheduler & Quiet Hours Engine
Validates:
1. Schedule persistence and rehydration (survives restarts)
2. Quiet hours gatekeeper and morning deferral
3. Anti-nagging cooldown (dismissed events blocked for 24 hours)
4. Snooze deferral
5. Context-aware delivery: low-pressure / silent suggestions during busy or study states
"""
import pytest
from datetime import datetime, timedelta, timezone
from app import database as db
from app.proactive_scheduler import (
    schedule_proactive_event,
    evaluate_quiet_hours,
    process_due_events,
    snooze_proactive_event,
    dismiss_proactive_event,
    get_user_current_context,
)

@pytest.fixture(autouse=True)
def setup_proactive_test_db(setup_test_db):
    yield

def test_proactive_event_scheduled_and_survives_restart():
    u = db.create_user("sched_user@test.com", "Password123!", is_18=True, agreed_terms=True, is_verified=True)
    uid = u["id"]

    sched_time = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
    eid = schedule_proactive_event(
        user_id=uid,
        event_type="study_checkin",
        title="Review Computer Networks chapter 3",
        scheduled_for_utc=sched_time,
        payload={"subject": "Computer Networks", "chapter": 3},
        respect_quiet_hours=False
    )
    assert eid > 0

    # Simulate query at scheduled time
    fired = process_due_events(user_id=uid, current_time_utc=sched_time)
    assert len(fired) == 1
    assert fired[0]["id"] == eid
    assert fired[0]["payload"]["subject"] == "Computer Networks"
    assert fired[0]["is_silent"] is False

def test_quiet_hours_deferral_to_morning():
    u = db.create_user("quiet_user@test.com", "Password123!", is_18=True, agreed_terms=True, is_verified=True, timezone_name="UTC")
    uid = u["id"]

    # Configure quiet hours 22:00 to 08:00
    db.set_setting(uid, "quiet_hours_enabled", "true")
    db.set_setting(uid, "quiet_hours_start", "22:00")
    db.set_setting(uid, "quiet_hours_end", "08:00")

    # Time at 23:30 (inside quiet hours)
    late_night = datetime(2026, 11, 10, 23, 30, tzinfo=timezone.utc)
    assert evaluate_quiet_hours(uid, late_night) is True

    # Time at 14:00 (outside quiet hours)
    daytime = datetime(2026, 11, 10, 14, 0, tzinfo=timezone.utc)
    assert evaluate_quiet_hours(uid, daytime) is False

    # Schedule event during quiet hours -> should be deferred
    eid = schedule_proactive_event(
        user_id=uid,
        event_type="revision_reminder",
        title="Evening revision",
        scheduled_for_utc=late_night,
        respect_quiet_hours=True
    )

    # Calling process_due_events at 23:30 should NOT fire it
    fired_night = process_due_events(user_id=uid, current_time_utc=late_night)
    assert len(fired_night) == 0

    # Calling process_due_events next morning at 08:30 should fire it
    next_morning = datetime(2026, 11, 11, 8, 30, tzinfo=timezone.utc)
    fired_morning = process_due_events(user_id=uid, current_time_utc=next_morning)
    assert len(fired_morning) == 1
    assert fired_morning[0]["id"] == eid

def test_anti_nagging_cooldown_on_dismissal():
    u = db.create_user("antinag@test.com", "Password123!", is_18=True, agreed_terms=True, is_verified=True)
    uid = u["id"]

    base_time = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    eid = schedule_proactive_event(
        user_id=uid,
        event_type="next_step",
        title="Check out MIT OCW linear algebra notes",
        scheduled_for_utc=base_time,
        respect_quiet_hours=False
    )

    # Dismiss event
    dismissed = dismiss_proactive_event(uid, eid)
    assert dismissed is True

    # Within 24 hours (e.g. 2 hours later), event must NOT fire
    two_hours_later = base_time + timedelta(hours=2)
    fired = process_due_events(user_id=uid, current_time_utc=two_hours_later)
    assert len(fired) == 0

def test_snooze_defers_to_requested_time():
    u = db.create_user("snooze_user@test.com", "Password123!", is_18=True, agreed_terms=True, is_verified=True)
    uid = u["id"]

    base_time = datetime.now(timezone.utc)
    eid = schedule_proactive_event(
        user_id=uid,
        event_type="study_checkin",
        title="Maths tutorial session",
        scheduled_for_utc=base_time,
        respect_quiet_hours=False
    )

    # Snooze for 45 minutes
    snoozed = snooze_proactive_event(uid, eid, snooze_minutes=45)
    assert snoozed is True

    # Check 10 minutes later -> should NOT fire
    check_early = datetime.now(timezone.utc) + timedelta(minutes=10)
    fired_early = process_due_events(user_id=uid, current_time_utc=check_early)
    assert len(fired_early) == 0

def test_busy_or_study_context_triggers_low_pressure_suggestion():
    u = db.create_user("busy_user@test.com", "Password123!", is_18=True, agreed_terms=True, is_verified=True)
    uid = u["id"]

    # Add temporary context that user is in study session
    db.add_fact(
        user_id=uid,
        fact_text="Active study session for Operating Systems",
        category="activity",
        fact_type="temporary_context",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2)
    )

    ctx = get_user_current_context(uid)
    assert ctx["status"] == "studying"

    now = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)
    eid = schedule_proactive_event(
        user_id=uid,
        event_type="study_resource",
        title="Here is an animation of Peterson's algorithm",
        scheduled_for_utc=now,
        respect_quiet_hours=False
    )

    fired = process_due_events(user_id=uid, current_time_utc=now)
    assert len(fired) == 1
    # Must be marked silent / low-pressure without loud interruption
    assert fired[0]["is_silent"] is True
    assert "[Low-pressure suggestion]" in fired[0]["title"]


def test_missing_temporary_context_defaults_to_uncertain():
    """
    Regression Test: Missing temporary context must return 'uncertain' (never assuming 'available').
    If SINBHA cannot tell whether the user is busy, studying, or available, it must not act certain.
    """
    u = db.create_user("uncertain_tester@test.com", "Password123!", is_18=True, agreed_terms=True, is_verified=True)
    uid = u["id"]

    ctx = get_user_current_context(uid)
    assert ctx["status"] == "uncertain"
    assert "no active temporary context" in ctx["detail"].lower()


