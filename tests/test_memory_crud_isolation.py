import pytest
import time
from fastapi.testclient import TestClient
from app import database as db
from app.main import app
from app.proactive_scheduler import schedule_proactive_event, list_user_proactive_events
from app.models import utc_now


@pytest.fixture
def user_a():
    email = f"user_a_{int(time.time() * 1000)}@sinbha.local"
    u = db.create_user(email, "PasswordA123!", "User Alpha", "UTC", is_verified=True)
    uid = u["id"] if isinstance(u, dict) else u
    token = db.create_session(uid)
    return {"id": uid, "email": email, "token": token}


@pytest.fixture
def user_b():
    email = f"user_b_{int(time.time() * 1000)}@sinbha.local"
    u = db.create_user(email, "PasswordB123!", "User Beta", "UTC", is_verified=True)
    uid = u["id"] if isinstance(u, dict) else u
    token = db.create_session(uid)
    return {"id": uid, "email": email, "token": token}


def test_fact_crud_lifecycle_and_export(user_a):
    """
    Verifies full lifecycle for personal memory facts:
    POST create -> GET read -> PUT update -> GET export -> DELETE single -> DELETE all.
    """
    client = TestClient(app)
    client.cookies.set("sinbha_session", user_a["token"])

    # 1. Create a fact
    create_res = client.post("/api/facts", json={
        "fact": "Preparing for AWS Solutions Architect exam",
        "category": "education",
        "fact_type": "current_goal",
        "source": "user_explicit",
        "confidence": 95,
        "is_sensitive": False
    })
    assert create_res.status_code == 200
    fact_id = create_res.json()["fact_id"]

    # 2. Read facts via /api/user/memory
    get_res = client.get("/api/user/memory")
    assert get_res.status_code == 200
    facts = get_res.json()["facts"]
    assert any(f["id"] == fact_id and f["fact"] == "Preparing for AWS Solutions Architect exam" for f in facts)
    assert get_res.json()["memory_enabled"] is True

    # 3. Update the fact via PUT /api/user/memory/{fact_id}
    put_res = client.put(f"/api/user/memory/{fact_id}", json={
        "fact": "Passed AWS Solutions Architect Associate exam",
        "category": "education",
        "confidence": 100
    })
    assert put_res.status_code == 200
    assert put_res.json()["success"] is True

    # Verify update persisted
    get_res2 = client.get("/api/user/memory")
    updated = next(f for f in get_res2.json()["facts"] if f["id"] == fact_id)
    assert updated["fact"] == "Passed AWS Solutions Architect Associate exam"
    assert updated["confidence"] == 100

    # 4. Export memory via GET /api/user/memory/export
    export_res = client.get("/api/user/memory/export")
    assert export_res.status_code == 200
    export_data = export_res.json()
    assert "user_id" in export_data
    assert "facts" in export_data
    assert any(f["id"] == fact_id for f in export_data["facts"])

    # 5. Delete individual fact via DELETE /api/user/memory/{fact_id}
    del_res = client.delete(f"/api/user/memory/{fact_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Verify fact is gone
    get_res3 = client.get("/api/user/memory")
    assert all(f["id"] != fact_id for f in get_res3.json()["facts"])


def test_multi_user_tenant_isolation(user_a, user_b):
    """
    Ensures strict tenant isolation:
    User B cannot read, update, delete, or export User A's facts or proactive events.
    """
    client_a = TestClient(app)
    client_a.cookies.set("sinbha_session", user_a["token"])

    client_b = TestClient(app)
    client_b.cookies.set("sinbha_session", user_b["token"])

    # User A creates a private fact
    create_a = client_a.post("/api/facts", json={
        "fact": "Secret project code: Project Titan",
        "category": "work",
        "fact_type": "current_goal",
        "confidence": 100
    })
    assert create_a.status_code == 200
    fact_a_id = create_a.json()["fact_id"]

    # User A schedules a proactive event
    evt_a_id = schedule_proactive_event(
        user_id=user_a["id"],
        event_type="study_reminder",
        title="User A Private Study",
        scheduled_for_utc=utc_now()
    )

    # 1. User B should NOT see User A's fact
    get_b = client_b.get("/api/user/memory")
    assert get_b.status_code == 200
    assert all(f["id"] != fact_a_id for f in get_b.json()["facts"])

    # 2. User B attempting to update User A's fact should receive 404
    put_b = client_b.put(f"/api/user/memory/{fact_a_id}", json={
        "fact": "Hacked content"
    })
    assert put_b.status_code == 404

    # 3. User B attempting to delete User A's fact should receive 404
    del_b = client_b.delete(f"/api/user/memory/{fact_a_id}")
    assert del_b.status_code == 404

    # 4. User B export should NOT contain User A's fact
    export_b = client_b.get("/api/user/memory/export")
    assert export_b.status_code == 200
    assert all(f["id"] != fact_a_id for f in export_b.json()["facts"])

    # 5. User B should NOT see User A's proactive events
    evts_b = client_b.get("/api/proactive/events")
    assert evts_b.status_code == 200
    assert all(e["id"] != evt_a_id for e in evts_b.json()["events"])

    # 6. User B attempting to complete User A's proactive event should receive 404
    comp_b = client_b.post(f"/api/proactive/events/{evt_a_id}/complete")
    assert comp_b.status_code == 404

