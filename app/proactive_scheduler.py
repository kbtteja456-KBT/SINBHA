"""
Pillar 2: Durable Proactive Scheduler & Quiet Hours Engine for SINBHA
Manages:
- Event-driven proactive reminders & study suggestions persisted in DB
- Resilient restart rehydration
- User timezone & quiet hours gatekeeping
- Anti-nagging cooldown (24-hour suppression upon dismissal)
- Snooze management
- Low-pressure suggestions when user context is busy/studying/uncertain
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo
from sqlalchemy import select, and_, or_, delete

from app.models import ProactiveEvent, User, utc_now
from app.database import get_db_session, get_setting, get_all_facts, log_audit

logger = logging.getLogger("sinbha.proactive_scheduler")

MAX_PROACTIVE_PER_DAY = 2

def get_user_timezone(user_id: int) -> str:
    """Gets the configured timezone for this user, default 'UTC'."""
    with get_db_session() as session:
        user = session.scalar(select(User).where(User.id == user_id))
        if user and user.timezone:
            return user.timezone.strip()
    return "UTC"

def evaluate_quiet_hours(user_id: int, target_dt_utc: Optional[datetime] = None) -> bool:
    """
    Checks if a target datetime (defaulting to utc_now) falls within the user's quiet hours.
    Respects user timezone and quiet_hours_enabled, quiet_hours_start, quiet_hours_end settings.
    """
    enabled = get_setting(user_id, "quiet_hours_enabled", "true")
    if str(enabled).lower() == "false":
        return False

    tz_str = get_user_timezone(user_id)
    try:
        user_tz = ZoneInfo(tz_str)
    except Exception:
        user_tz = timezone.utc

    now_utc = target_dt_utc or utc_now()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    user_local = now_utc.astimezone(user_tz)
    current_time_str = user_local.strftime("%H:%M")

    start_str = get_setting(user_id, "quiet_hours_start", "22:00")
    end_str = get_setting(user_id, "quiet_hours_end", "08:00")

    if start_str > end_str:
        # Crosses midnight (e.g. 22:00 to 08:00)
        return current_time_str >= start_str or current_time_str < end_str
    else:
        # Same day (e.g. 13:00 to 15:00)
        return start_str <= current_time_str < end_str

def get_next_quiet_hours_end_utc(user_id: int, base_dt_utc: Optional[datetime] = None) -> datetime:
    """Calculates the UTC datetime for the next end of quiet hours (morning window)."""
    tz_str = get_user_timezone(user_id)
    try:
        user_tz = ZoneInfo(tz_str)
    except Exception:
        user_tz = timezone.utc

    now_utc = base_dt_utc or utc_now()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    user_local = now_utc.astimezone(user_tz)
    end_str = get_setting(user_id, "quiet_hours_end", "08:00")
    try:
        end_hour, end_min = map(int, end_str.split(":"))
    except Exception:
        end_hour, end_min = 8, 0

    candidate_local = user_local.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
    if candidate_local <= user_local:
        candidate_local += timedelta(days=1)

    return candidate_local.astimezone(timezone.utc)

def schedule_proactive_event(
    user_id: int,
    event_type: str,
    title: str,
    scheduled_for_utc: datetime,
    payload: Optional[Dict[str, Any]] = None,
    respect_quiet_hours: bool = True
) -> int:
    """
    Persists a durable proactive event in the database.
    Survives app and backend restarts. Automatically defers non-emergency events
    scheduled during quiet hours to the morning window.
    """
    if scheduled_for_utc.tzinfo is None:
        scheduled_for_utc = scheduled_for_utc.replace(tzinfo=timezone.utc)

    init_status = "pending"
    effective_sched = scheduled_for_utc

    if respect_quiet_hours and evaluate_quiet_hours(user_id, scheduled_for_utc):
        effective_sched = get_next_quiet_hours_end_utc(user_id, scheduled_for_utc)
        init_status = "deferred_quiet_hours"

    payload_str = json.dumps(payload or {})

    with get_db_session() as session:
        evt = ProactiveEvent(
            user_id=user_id,
            event_type=event_type,
            title=title.strip(),
            payload_json=payload_str,
            scheduled_for_utc=effective_sched,
            status=init_status,
            created_at=utc_now()
        )
        session.add(evt)
        session.flush()
        log_audit(user_id, "PROACTIVE_EVENT_SCHEDULED", f"Event #{evt.id} ({event_type}) for {effective_sched.isoformat()}", session=session)
        return evt.id

def snooze_proactive_event(user_id: int, event_id: int, snooze_minutes: int = 30) -> bool:
    """Snoozes a proactive event for the requested minutes."""
    with get_db_session() as session:
        evt = session.scalar(select(ProactiveEvent).where(ProactiveEvent.id == event_id, ProactiveEvent.user_id == user_id))
        if not evt:
            return False
        new_time = utc_now() + timedelta(minutes=max(5, snooze_minutes))
        evt.snoozed_until = new_time
        evt.scheduled_for_utc = new_time
        evt.status = "snoozed"
        log_audit(user_id, "PROACTIVE_EVENT_SNOOZED", f"Event #{event_id} snoozed until {new_time.isoformat()}", session=session)
        return True

def dismiss_proactive_event(user_id: int, event_id: int) -> bool:
    """
    Dismisses a proactive event and sets a 24-hour anti-nag cooldown for this topic/type.
    """
    with get_db_session() as session:
        evt = session.scalar(select(ProactiveEvent).where(ProactiveEvent.id == event_id, ProactiveEvent.user_id == user_id))
        if not evt:
            return False
        evt.status = "dismissed"
        evt.dismissed_until = utc_now() + timedelta(hours=24)
        log_audit(user_id, "PROACTIVE_EVENT_DISMISSED", f"Event #{event_id} dismissed with 24h cooldown", session=session)
        return True

def get_user_current_context(user_id: int) -> Dict[str, Any]:
    """Inspects temporary context memory to determine if user is busy or studying."""
    facts = get_all_facts(user_id, fact_type="temporary_context")
    if not facts:
        return {"status": "uncertain", "detail": "No active temporary context"}
    # Check latest temporary context
    latest = facts[0]
    txt = latest.get("fact", "").lower()
    if any(k in txt for k in ("study", "exam", "reading", "library")):
        return {"status": "studying", "detail": latest.get("fact")}
    if any(k in txt for k in ("busy", "meeting", "work", "class", "commute", "sleep")):
        return {"status": "busy", "detail": latest.get("fact")}
    return {"status": "uncertain", "detail": latest.get("fact")}

def process_due_events(user_id: Optional[int] = None, current_time_utc: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """
    Processes and fires pending events that are due.
    Enforces quiet hours, anti-nagging cooldowns, and daily frequency limits.
    """
    now = current_time_utc or utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    fired_events = []

    with get_db_session() as session:
        query = select(ProactiveEvent).where(
            or_(
                ProactiveEvent.status == "pending",
                ProactiveEvent.status == "deferred_quiet_hours",
                and_(ProactiveEvent.status == "snoozed", ProactiveEvent.snoozed_until <= now)
            ),
            ProactiveEvent.scheduled_for_utc <= now
        )
        if user_id is not None:
            query = query.where(ProactiveEvent.user_id == user_id)

        events = session.scalars(query).all()

        for evt in events:
            # 1. Check quiet hours now
            if evaluate_quiet_hours(evt.user_id, now):
                # Still in quiet hours, re-defer
                evt.scheduled_for_utc = get_next_quiet_hours_end_utc(evt.user_id, now)
                evt.status = "deferred_quiet_hours"
                continue

            # 2. Check 24-hour anti-nag cooldown on dismissed topics
            if evt.dismissed_until and evt.dismissed_until > now:
                continue

            # 3. Contextual inspection: busy / studying / uncertain
            context = get_user_current_context(evt.user_id)
            is_silent = False
            msg_prefix = ""
            if context["status"] in ("busy", "studying"):
                # Deliver as low-pressure silent suggestion without loud interruption
                is_silent = True
                msg_prefix = "[Low-pressure suggestion] "

            try:
                payload = json.loads(evt.payload_json or "{}")
            except Exception:
                payload = {}

            evt.status = "fired"
            fired_events.append({
                "id": evt.id,
                "user_id": evt.user_id,
                "event_type": evt.event_type,
                "title": f"{msg_prefix}{evt.title}",
                "payload": payload,
                "is_silent": is_silent,
                "fired_at": now.isoformat()
            })
            log_audit(evt.user_id, "PROACTIVE_EVENT_FIRED", f"Fired event #{evt.id} ({evt.event_type}, silent={is_silent})", session=session)

    return fired_events


async def process_and_deliver_due_events(
    user_id: Optional[int] = None,
    relay_manager: Optional[Any] = None,
    current_time_utc: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """
    Durable execution path (survives backend / companion restarts):
    1. Finds due proactive events from persistent storage.
    2. Enforces quiet hours, anti-nagging cooldowns, and user context.
    3. DELIVERS each due event to the user:
       - Persists assistant message to conversation transcript via db.save_message
       - Broadcasts to connected websockets and relays to devices via relay_manager
       - Updates event status to 'delivered' with delivered_at timestamp.
    4. Returns list of delivered event descriptors.
    """
    now = current_time_utc or utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    delivered_events = []

    with get_db_session() as session:
        query = select(ProactiveEvent).where(
            or_(
                ProactiveEvent.status == "pending",
                ProactiveEvent.status == "deferred_quiet_hours",
                and_(ProactiveEvent.status == "snoozed", ProactiveEvent.snoozed_until <= now)
            ),
            ProactiveEvent.scheduled_for_utc <= now
        )
        if user_id is not None:
            query = query.where(ProactiveEvent.user_id == user_id)

        events = session.scalars(query).all()

        for evt in events:
            # 1. Quiet hours check
            if evaluate_quiet_hours(evt.user_id, now):
                evt.scheduled_for_utc = get_next_quiet_hours_end_utc(evt.user_id, now)
                evt.status = "deferred_quiet_hours"
                continue

            # 2. 24-hour anti-nagging cooldown
            if evt.dismissed_until and evt.dismissed_until > now:
                continue

            # 3. Contextual inspection: busy / studying / uncertain
            context = get_user_current_context(evt.user_id)
            is_silent = False
            msg_prefix = ""
            if context["status"] in ("busy", "studying"):
                is_silent = True
                msg_prefix = "[Low-pressure suggestion] "

            try:
                payload = json.loads(evt.payload_json or "{}")
            except Exception:
                payload = {}

            display_title = f"{msg_prefix}{evt.title}"
            message_content = display_title
            if payload.get("suggestion"):
                message_content += f"\n\n{payload['suggestion']}"
            elif payload.get("subject"):
                message_content += f" ({payload['subject']})"

            # 4. DELIVER to User Conversation Transcript
            transcript_saved = False
            try:
                from app.database import save_message
                msg_id = save_message(user_id=evt.user_id, role="assistant", content=message_content)
                if msg_id:
                    transcript_saved = True
            except Exception as e:
                logger.warning(f"Failed to save proactive message to transcript for event #{evt.id}: {e}")

            # 5. DELIVER to Connected Devices / Websockets
            ws_delivered = False
            if relay_manager is not None:
                packet = {
                    "type": "proactive_event",
                    "event_id": evt.id,
                    "event_type": evt.event_type,
                    "title": display_title,
                    "content": message_content,
                    "is_silent": is_silent,
                    "timestamp": now.timestamp(),
                }
                try:
                    import inspect
                    if hasattr(relay_manager, "broadcast_to_user"):
                        res = relay_manager.broadcast_to_user(evt.user_id, packet)
                        if inspect.iscoroutine(res):
                            await res
                        ws_delivered = True
                    elif hasattr(relay_manager, "active_websockets"):
                        msg_str = json.dumps(packet)
                        for (uid, dev_id), ws in list(relay_manager.active_websockets.items()):
                            if uid == evt.user_id:
                                try:
                                    ws_res = ws.send_text(msg_str)
                                    if inspect.iscoroutine(ws_res):
                                        await ws_res
                                    ws_delivered = True
                                except Exception:
                                    pass
                except Exception as e:
                    logger.warning(f"Failed to deliver proactive websocket packet for event #{evt.id}: {e}")

            # If neither transcript saved nor websocket delivered, do NOT mark delivered!
            if not transcript_saved and not ws_delivered:
                evt.status = "delivery_failed"
                session.flush()
                log_audit(
                    evt.user_id,
                    "PROACTIVE_EVENT_DELIVERY_FAILED",
                    f"Delivery failed for event #{evt.id} ({evt.event_type}) - neither transcript nor websocket succeeded",
                    session=session
                )
                continue

            # 6. Mark delivered in database
            evt.status = "delivered"
            evt.delivered_at = now
            session.flush()

            log_audit(
                evt.user_id,
                "PROACTIVE_EVENT_DELIVERED",
                f"Delivered event #{evt.id} ({evt.event_type}) to user/devices (silent={is_silent})",
                session=session
            )

            delivered_events.append({
                "id": evt.id,
                "user_id": evt.user_id,
                "event_type": evt.event_type,
                "title": display_title,
                "content": message_content,
                "is_silent": is_silent,
                "delivered_at": now.isoformat()
            })

    return delivered_events


def complete_proactive_event(user_id: int, event_id: int) -> bool:
    """Marks a proactive event as completed."""
    with get_db_session() as session:
        evt = session.scalar(select(ProactiveEvent).where(ProactiveEvent.id == event_id, ProactiveEvent.user_id == user_id))
        if not evt:
            return False
        evt.status = "completed"
        evt.completed_at = utc_now()
        log_audit(user_id, "PROACTIVE_EVENT_COMPLETED", f"Event #{event_id} marked completed", session=session)
        return True


def reschedule_proactive_event(user_id: int, event_id: int, new_scheduled_for_utc: datetime) -> bool:
    """Reschedules a proactive event to a new UTC datetime."""
    if new_scheduled_for_utc.tzinfo is None:
        new_scheduled_for_utc = new_scheduled_for_utc.replace(tzinfo=timezone.utc)
    with get_db_session() as session:
        evt = session.scalar(select(ProactiveEvent).where(ProactiveEvent.id == event_id, ProactiveEvent.user_id == user_id))
        if not evt:
            return False
        evt.scheduled_for_utc = new_scheduled_for_utc
        evt.status = "pending"
        evt.snoozed_until = None
        log_audit(user_id, "PROACTIVE_EVENT_RESCHEDULED", f"Event #{event_id} rescheduled to {new_scheduled_for_utc.isoformat()}", session=session)
        return True


def list_user_proactive_events(user_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lists proactive events for a user, optionally filtered by status."""
    with get_db_session() as session:
        query = select(ProactiveEvent).where(ProactiveEvent.user_id == user_id)
        if status:
            query = query.where(ProactiveEvent.status == status)
        query = query.order_by(ProactiveEvent.scheduled_for_utc.asc())
        events = session.scalars(query).all()
        result = []
        for evt in events:
            try:
                payload = json.loads(evt.payload_json or "{}")
            except Exception:
                payload = {}
            result.append({
                "id": evt.id,
                "user_id": evt.user_id,
                "event_type": evt.event_type,
                "title": evt.title,
                "payload": payload,
                "scheduled_for_utc": evt.scheduled_for_utc.isoformat() if evt.scheduled_for_utc else None,
                "status": evt.status,
                "snoozed_until": evt.snoozed_until.isoformat() if evt.snoozed_until else None,
                "dismissed_until": evt.dismissed_until.isoformat() if evt.dismissed_until else None,
                "delivered_at": evt.delivered_at.isoformat() if evt.delivered_at else None,
                "completed_at": evt.completed_at.isoformat() if hasattr(evt, "completed_at") and evt.completed_at else None,
                "created_at": evt.created_at.isoformat() if evt.created_at else None,
            })
        return result

