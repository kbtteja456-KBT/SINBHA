"""
Integration Test for Proactive Scheduler Durable Execution & Delivery (Task 1)
Proves that due events actually REACH the user and connected device,
not just that they are stored in the database.
"""

import pytest
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from app import database as db
from app.models import ProactiveEvent
from app.proactive_scheduler import (
    schedule_proactive_event,
    process_and_deliver_due_events,
)
from app.device_relay import CommandRelayManager


@pytest.fixture(autouse=True)
def setup_test_environment(setup_test_db):
    yield


@pytest.mark.asyncio
async def test_due_proactive_event_reaches_user_and_device_after_restart():
    """
    Integration test proving:
    1. A proactive event scheduled in the past (e.g. while server was shut down) is picked up.
    2. It is durably DELIVERED to the user's chat transcript as an assistant message.
    3. It is durably DELIVERED over the device connection/websocket to the paired hardware.
    4. Database status transitions from 'pending' -> 'delivered' with delivered_at recorded.
    """
    # 1. Create user and paired device
    user = db.create_user("delivery_test@sinbha.local", "Password123!", is_18=True, agreed_terms=True, is_verified=True)
    uid = user["id"]

    # 2. Setup mock device connection on relay manager
    relay = CommandRelayManager()
    mock_phone_ws = AsyncMock()
    relay.active_websockets[(uid, "test_phone_01")] = mock_phone_ws

    # 3. Schedule proactive event that was due 15 minutes ago (simulating backend was offline)
    past_due_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    event_id = schedule_proactive_event(
        user_id=uid,
        event_type="study_checkin",
        title="Check-in: How is your Operating Systems revision going?",
        scheduled_for_utc=past_due_time,
        payload={"subject": "Operating Systems", "suggestion": "Try reviewing virtual memory pages before tomorrow."},
        respect_quiet_hours=False
    )
    assert event_id > 0

    # Verify event is initially pending in database
    with db.get_db_session() as sess:
        evt = sess.scalar(db.select(ProactiveEvent).where(ProactiveEvent.id == event_id))
        assert evt.status == "pending"
        assert evt.delivered_at is None

    # Verify user conversation has 0 messages initially
    messages_before = db.get_recent_messages(uid, limit=10)
    assert len(messages_before) == 0

    # 4. Trigger durable startup / background delivery pipeline
    delivered = await process_and_deliver_due_events(user_id=uid, relay_manager=relay)
    assert len(delivered) == 1
    assert delivered[0]["id"] == event_id
    assert "Operating Systems" in delivered[0]["title"]

    # 5. PROVE IT REACHED THE USER: Check conversation transcript in database
    messages_after = db.get_recent_messages(uid, limit=10)
    assert len(messages_after) == 1
    msg = messages_after[0]
    assert msg["role"] == "assistant"
    assert "How is your Operating Systems revision going?" in msg["content"]
    assert "virtual memory" in msg["content"]

    # 6. PROVE IT REACHED THE DEVICE: Check websocket packet delivered to phone
    assert mock_phone_ws.send_text.called
    sent_call_args = mock_phone_ws.send_text.call_args[0][0]
    packet = json.loads(sent_call_args)
    assert packet["type"] == "proactive_event"
    assert packet["event_id"] == event_id
    assert "Operating Systems" in packet["title"]

    # 7. PROVE PERSISTENT STATUS: Status is now 'delivered' with delivered_at
    with db.get_db_session() as sess:
        updated_evt = sess.scalar(db.select(ProactiveEvent).where(ProactiveEvent.id == event_id))
        assert updated_evt.status == "delivered"
        assert updated_evt.delivered_at is not None

    # 8. PROVE IDEMPOTENCE: Re-running delivery does NOT duplicate the message
    delivered_again = await process_and_deliver_due_events(user_id=uid, relay_manager=relay)
    assert len(delivered_again) == 0
    messages_final = db.get_recent_messages(uid, limit=10)
    assert len(messages_final) == 1

