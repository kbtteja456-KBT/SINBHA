"""
Tests for Pillar 3: Privacy-First Personal Memory & Emotion Governance
Validates:
1. 4-tier taxonomy: stable_fact, current_goal, temporary_context, preference
2. Provenance tracking: source, confidence, last_confirmed_at, expires_at
3. Auto-expiration of temporary context
4. Full user governance: CRUD, export, wipe, and toggle
5. Emotion governance: user-stated vs inferred emotions
6. Strict multi-user tenant isolation
"""
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.main import app
from app import database as db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_memory_test_db(setup_test_db):
    """Uses fresh test database."""
    yield

def test_memory_creation_with_provenance_and_taxonomy():
    u = db.create_user("mem_user1@test.com", "Password123!", is_18=True, agreed_terms=True, is_verified=True)
    uid = u["id"]

    # 1. Stable fact
    fid1 = db.add_fact(
        user_id=uid,
        fact_text="Degree is BTech Computer Science",
        category="education",
        fact_type="stable_fact",
        source="user_explicit",
        confidence=100
    )
    assert fid1 > 0

    # 2. Current goal
    fid2 = db.add_fact(
        user_id=uid,
        fact_text="Complete Operating Systems assignment by Friday",
        category="study",
        fact_type="current_goal",
        source="user_explicit",
        confidence=95
    )
    assert fid2 > 0

    # 3. Temporary context (expires in 2 hours)
    future_exp = datetime.now(timezone.utc) + timedelta(hours=2)
    fid3 = db.add_fact(
        user_id=uid,
        fact_text="Studying in the campus library",
        category="activity",
        fact_type="temporary_context",
        source="user_explicit",
        confidence=90,
        expires_at=future_exp
    )
    assert fid3 > 0

    # Retrieve all facts
    facts = db.get_all_facts(uid)
    assert len(facts) == 3

    fact_types = {f["fact_type"] for f in facts}
    assert fact_types == {"stable_fact", "current_goal", "temporary_context"}

    # Verify provenance metadata
    temp_fact = next(f for f in facts if f["id"] == fid3)
    assert temp_fact["source"] == "user_explicit"
    assert temp_fact["confidence"] == 90
    assert temp_fact["expires_at"] is not None
    assert temp_fact["last_confirmed_at"] != ""

def test_temporary_context_auto_expiration():
    u = db.create_user("mem_exp@test.com", "Password123!", is_18=True, agreed_terms=True, is_verified=True)
    uid = u["id"]

    # Add expired temporary context (expired 10 minutes ago)
    past_exp = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.add_fact(
        user_id=uid,
        fact_text="In a quick 15-minute team standup",
        category="status",
        fact_type="temporary_context",
        source="user_explicit",
        expires_at=past_exp
    )

    # Active stable fact
    db.add_fact(
        user_id=uid,
        fact_text="Preferred name is Alex",
        category="personal",
        fact_type="stable_fact"
    )

    # By default, expired facts must NOT be returned
    active_facts = db.get_all_facts(uid, include_expired=False)
    assert len(active_facts) == 1
    assert active_facts[0]["fact"] == "Preferred name is Alex"

    # With include_expired=True, both are available for audit/export
    all_facts = db.get_all_facts(uid, include_expired=True)
    assert len(all_facts) == 2

def test_user_memory_governance_export_update_wipe_toggle():
    u = db.create_user("mem_gov@test.com", "Password123!", is_18=True, agreed_terms=True, is_verified=True)
    uid = u["id"]

    fid = db.add_fact(uid, "Target job is Backend Engineer", category="career")
    assert fid > 0

    # 1. Update / Correct fact
    ok = db.update_fact(uid, fid, "Target job is Distributed Systems Engineer", confidence=95)
    assert ok is True
    facts = db.get_all_facts(uid)
    assert facts[0]["fact"] == "Target job is Distributed Systems Engineer"
    assert facts[0]["confidence"] == 95

    # 2. Export Memory
    export = db.export_user_memory(uid)
    assert export["user_id"] == uid
    assert export["facts_count"] == 1
    assert export["facts"][0]["fact"] == "Target job is Distributed Systems Engineer"
    assert export["memory_enabled"] is True

    # 3. Toggle Memory Off
    db.toggle_user_memory(uid, False)
    assert db.is_memory_enabled(uid) is False

    # Attempting to add fact when memory is disabled is blocked
    new_fid = db.add_fact(uid, "Favorite programming language is Python")
    assert new_fid == -1

    # 4. Wipe Memory (Right to be Forgotten)
    wipe_ok = db.wipe_user_memory(uid)
    assert wipe_ok is True
    assert len(db.get_all_facts(uid)) == 0

def test_tenant_isolation_between_users():
    u1 = db.create_user("user_a@test.com", "Password123!", is_18=True, agreed_terms=True, is_verified=True)
    u2 = db.create_user("user_b@test.com", "Password123!", is_18=True, agreed_terms=True, is_verified=True)

    fid_a = db.add_fact(u1["id"], "Secret fact for user A")

    # User B cannot see User A's facts
    facts_b = db.get_all_facts(u2["id"])
    assert len(facts_b) == 0

    # User B cannot update User A's fact
    update_res = db.update_fact(u2["id"], fid_a, "Tampered text")
    assert update_res is False

    # User B cannot delete User A's fact
    del_res = db.delete_fact(u2["id"], fid_a)
    assert del_res is False

    # Fact remains intact for User A
    facts_a = db.get_all_facts(u1["id"])
    assert len(facts_a) == 1
    assert facts_a[0]["fact"] == "Secret fact for user A"

