import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from app import database as db
from app.models import utc_now, ProactiveEvent
from app.agent_tools import handle_manage_study_plan
from app.proactive_scheduler import (
    process_and_deliver_due_events,
    snooze_proactive_event,
    dismiss_proactive_event,
    complete_proactive_event,
    reschedule_proactive_event,
    list_user_proactive_events,
    schedule_proactive_event,
)


import time

@pytest.fixture
def test_user():
    email = f"student_proactive_{int(time.time() * 1000)}@sinbha.local"
    user = db.create_user(email, "Password123!", "Student Proactive", "UTC", is_verified=True)
    u_id = user["id"] if isinstance(user, dict) else user
    return u_id


@pytest.mark.asyncio
async def test_organize_subjects_workflow_creates_proactive_events(test_user):
    """
    Verifies that calling handle_manage_study_plan with action='organize_subjects'
    automatically schedules spaced repetition proactive events (Day 1, 3, 7) for each subject.
    """
    ctx = {"db": db}
    res = await handle_manage_study_plan(
        test_user,
        {"action": "organize_subjects", "degree": "B.Tech Computer Science", "subjects": ["Data Structures", "Algorithms"]},
        ctx
    )
    assert res["success"] is True
    assert res["revision_milestones_created"] == 6

    # Verify proactive events scheduled in DB
    events = list_user_proactive_events(test_user)
    assert len(events) >= 6
    ds_events = [e for e in events if "Data Structures" in e["title"]]
    algo_events = [e for e in events if "Algorithms" in e["title"]]
    assert len(ds_events) == 3
    assert len(algo_events) == 3

    # Check Day 1, 3, 7 titles
    titles = [e["title"] for e in ds_events]
    assert any("Day 1 review" in t for t in titles)
    assert any("Day 3 quiz" in t for t in titles)
    assert any("Day 7 practice" in t for t in titles)


@pytest.mark.asyncio
async def test_schedule_revision_and_track_assignment_workflow(test_user):
    """
    Verifies that scheduling a revision topic and tracking an assignment
    create appropriate proactive reminder events in DB.
    """
    ctx = {"db": db}
    rev_res = await handle_manage_study_plan(
        test_user,
        {"action": "schedule_revision", "subject": "Operating Systems", "topic": "Virtual Memory"},
        ctx
    )
    assert rev_res["success"] is True

    assign_res = await handle_manage_study_plan(
        test_user,
        {"action": "track_assignment", "subject": "Operating Systems", "assignment_title": "Page Replacement Lab", "due_date": "Friday"},
        ctx
    )
    assert assign_res["success"] is True

    events = list_user_proactive_events(test_user)
    os_revs = [e for e in events if "Virtual Memory" in e["title"]]
    assert len(os_revs) == 3

    deadline_alerts = [e for e in events if e["event_type"] == "deadline_alert"]
    assert len(deadline_alerts) >= 1
    assert any("Page Replacement Lab" in e["title"] for e in deadline_alerts)


def test_create_task_with_due_datetime_schedules_proactive_event(test_user):
    """
    Verifies that create_task automatically schedules a deadline alert
    when due_datetime_utc is supplied.
    """
    future_due = utc_now() + timedelta(days=2)
    task_id = db.create_task(
        user_id=test_user,
        title="Submit Thesis Draft",
        due_datetime_utc=future_due
    )
    assert isinstance(task_id, int)

    events = list_user_proactive_events(test_user)
    thesis_events = [e for e in events if "Thesis Draft" in e["title"]]
    assert len(thesis_events) == 1
    assert thesis_events[0]["event_type"] == "deadline_alert"


@pytest.mark.asyncio
async def test_proactive_delivery_failure_protection(test_user):
    """
    Verifies that if delivery fails (neither chat message saved nor websocket delivered),
    the event is NOT marked 'delivered', but marked 'delivery_failed'.
    """
    now = utc_now()
    evt_id = schedule_proactive_event(
        user_id=test_user,
        event_type="test_event",
        title="Important Alert",
        scheduled_for_utc=now - timedelta(minutes=5),
        respect_quiet_hours=False
    )

    # Patch save_message to raise an exception, and provide no relay_manager
    with patch("app.database.save_message", side_effect=RuntimeError("Database write error")):
        delivered = await process_and_deliver_due_events(
            user_id=test_user,
            relay_manager=None,
            current_time_utc=now
        )
        assert len(delivered) == 0

    # Verify event status in DB is delivery_failed, NOT delivered
    events = list_user_proactive_events(test_user)
    target = next(e for e in events if e["id"] == evt_id)
    assert target["status"] == "delivery_failed"
    assert target["delivered_at"] is None


@pytest.mark.asyncio
async def test_proactive_event_actions_lifecycle(test_user):
    """
    Verifies the complete user action lifecycle on proactive events:
    snooze -> anti-nag dismiss (24h cooldown) -> reschedule -> complete.
    """
    now = utc_now()
    evt_id = schedule_proactive_event(
        user_id=test_user,
        event_type="revision_reminder",
        title="Revise Database Indexing",
        scheduled_for_utc=now - timedelta(minutes=1),
        respect_quiet_hours=False
    )

    # 1. Snooze
    assert snooze_proactive_event(test_user, evt_id, snooze_minutes=45) is True
    evts = list_user_proactive_events(test_user, status="snoozed")
    assert len(evts) == 1
    assert evts[0]["id"] == evt_id

    # 2. Dismiss (enforces 24h anti-nagging cooldown)
    assert dismiss_proactive_event(test_user, evt_id) is True
    evts = list_user_proactive_events(test_user, status="dismissed")
    assert len(evts) == 1
    assert evts[0]["dismissed_until"] is not None

    # Verify process_and_deliver_due_events respects the 24h dismissal
    delivered = await process_and_deliver_due_events(
        user_id=test_user,
        current_time_utc=now + timedelta(hours=2)
    )
    assert all(d["id"] != evt_id for d in delivered)

    # 3. Reschedule
    new_time = now + timedelta(days=4)
    assert reschedule_proactive_event(test_user, evt_id, new_time) is True
    evts = list_user_proactive_events(test_user, status="pending")
    target = next(e for e in evts if e["id"] == evt_id)
    assert "status" in target and target["status"] == "pending"

    # 4. Complete
    assert complete_proactive_event(test_user, evt_id) is True
    evts = list_user_proactive_events(test_user, status="completed")
    assert any(e["id"] == evt_id for e in evts)
