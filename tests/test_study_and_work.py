"""
Tests for Phase 4: Gated Study, Career, and Messaging Assistance
Validates:
1. Study plan organization, spaced revision (Day 1, 3, 7), and assignment tracking.
2. Degree and subjects stored truthfully as stable facts in memory.
3. Curated learning resources with working links and concise explanations.
4. Career and job application tracking:
   - Bookmark, resume bullet drafting, and form prefill.
   - Strict action gating: Submitting or contacting employers WITHOUT explicit user approval is strictly blocked.
   - Submitting WITH explicit user approval is recorded truthfully.
5. Message drafting adapts to user communication style stored in memory, with strict action gating.
"""

import pytest
import time
from app import database as db
from app.agent_tools import (
    handle_manage_study_plan,
    handle_recommend_study_resource,
    handle_track_job_application,
)
from app.messages_assistant import draft_whatsapp_reply


@pytest.fixture
def study_user():
    email = f"study_user_{int(time.time() * 1000)}@sinbha.local"
    user = db.create_user(email, "hashed_pw", "Study Tester", "UTC")
    u_id = user["id"] if isinstance(user, dict) else user
    return {"id": u_id, "email": email}


# ============================================================================
# 1. STUDY PLAN MANAGEMENT & MEMORY INTEGRATION
# ============================================================================

@pytest.mark.asyncio
async def test_organize_study_plan_stores_facts_and_creates_spaced_revisions(study_user):
    """
    Organizing subjects for a degree:
    - Stores degree and subjects as stable_fact in memory.
    - Creates spaced repetition tasks (Day 1, Day 3, Day 7).
    """
    uid = study_user["id"]
    ctx = {"user_name": "Study Tester"}
    args = {
        "action": "organize_subjects",
        "degree": "BTech Computer Science & Engineering",
        "subjects": ["Data Structures", "Operating Systems"],
    }

    res = await handle_manage_study_plan(uid, args, ctx)
    assert res["success"] is True
    assert res["action"] == "organize_subjects"
    assert res["revision_milestones_created"] == 6  # 3 per subject (Day 1, 3, 7)

    # Verify facts were stored as stable_fact in personal memory
    facts = db.get_all_facts(uid)
    degree_facts = [f for f in facts if "BTech Computer Science" in f["fact"]]
    assert len(degree_facts) == 1
    assert degree_facts[0]["fact_type"] == "stable_fact"
    assert degree_facts[0]["source"] == "user_explicit"

    subj_facts = [f for f in facts if "Subject:" in f["fact"]]
    assert len(subj_facts) == 2
    for sf in subj_facts:
        assert sf["fact_type"] == "stable_fact"
        assert sf["source"] == "user_explicit"


@pytest.mark.asyncio
async def test_schedule_revision_and_track_assignment(study_user):
    """Scheduling revision creates spaced recall sessions; tracking assignments creates dated tasks."""
    uid = study_user["id"]
    ctx = {}

    # Schedule revision
    rev_res = await handle_manage_study_plan(
        uid,
        {
            "action": "schedule_revision",
            "subject": "Operating Systems",
            "topic": "Virtual Memory and Paging",
        },
        ctx,
    )
    assert rev_res["success"] is True
    assert len(rev_res["revision_tasks"]) == 3

    # Track assignment
    assign_res = await handle_manage_study_plan(
        uid,
        {
            "action": "track_assignment",
            "subject": "Data Structures",
            "assignment_title": "Implement AVL Tree and Red-Black Tree",
            "due_date": "Next Monday at 5:00 PM",
        },
        ctx,
    )
    assert assign_res["success"] is True
    assert "Implement AVL Tree" in assign_res["assignment"]

    # List plan
    list_res = await handle_manage_study_plan(uid, {"action": "list_plan"}, ctx)
    assert list_res["success"] is True
    assert list_res["pending_study_tasks"] >= 4


# ============================================================================
# 2. CURATED LEARNING RESOURCES
# ============================================================================

@pytest.mark.asyncio
async def test_recommend_study_resources_returns_working_urls_with_explanations(study_user):
    """Recommending study resources returns genuine URLs and concise explanations."""
    uid = study_user["id"]
    ctx = {}

    # Query OS
    res_os = await handle_recommend_study_resource(uid, {"subject": "Operating Systems", "topic": "Kernel"}, ctx)
    assert res_os["success"] is True
    assert res_os["resources_count"] >= 1
    os_urls = [r["url"] for r in res_os["resources"]]
    assert any("pages.cs.wisc.edu" in u or "nptel.ac.in" in u for u in os_urls)
    for r in res_os["resources"]:
        assert r["url"].startswith("http")
        assert len(r["reason"]) > 10

    # Query DSA
    res_dsa = await handle_recommend_study_resource(uid, {"subject": "Data Structures", "topic": "Binary Tree"}, ctx)
    assert res_dsa["success"] is True
    dsa_urls = [r["url"] for r in res_dsa["resources"]]
    assert any("ocw.mit.edu" in u or "geeksforgeeks.org" in u for u in dsa_urls)

    # General / Fallback
    res_gen = await handle_recommend_study_resource(uid, {"subject": "Astronomy and Quantum Physics"}, ctx)
    assert res_gen["success"] is True
    assert any("nptel.ac.in" in r["url"] or "ocw.mit.edu" in r["url"] for r in res_gen["resources"])


# ============================================================================
# 3. JOB APPLICATION TRACKING & CRITICAL ACTION GATING
# ============================================================================

@pytest.mark.asyncio
async def test_job_application_safe_tracking_and_drafting(study_user):
    """Bookmarking, drafting resume points, and prefill are safe non-destructive actions."""
    uid = study_user["id"]
    ctx = {"user_name": "Study Tester"}

    # Bookmark job
    bm_res = await handle_track_job_application(
        uid,
        {
            "action": "bookmark",
            "company": "Anthropic",
            "role": "Systems Engineer",
            "job_url": "https://example.com/jobs/systems",
            "deadline": "Dec 15, 2026",
        },
        ctx,
    )
    assert bm_res["success"] is True
    assert bm_res["company"] == "Anthropic"

    # Draft resume bullets
    draft_res = await handle_track_job_application(
        uid,
        {
            "action": "draft_resume_points",
            "company": "Anthropic",
            "role": "Systems Engineer",
            "experience_summary": "Built distributed caching layer in Python and C++",
        },
        ctx,
    )
    assert draft_res["success"] is True
    assert len(draft_res["draft_bullets"]) == 3

    # Prefill form
    prefill_res = await handle_track_job_application(
        uid,
        {
            "action": "prefill_form",
            "company": "Anthropic",
            "role": "Systems Engineer",
            "job_url": "https://example.com/jobs/systems",
        },
        ctx,
    )
    assert prefill_res["success"] is True
    assert prefill_res["prefilled_data"]["applicant_name"] == "Study Tester"


@pytest.mark.asyncio
async def test_job_application_submission_strictly_action_gated(study_user):
    """
    CRITICAL INVARIANT:
    Automatic submission or contacting employer is strictly ACTION GATED.
    Without explicit confirmation, it MUST refuse to submit.
    """
    uid = study_user["id"]
    ctx = {}

    # Attempt to submit WITHOUT confirmation
    unapproved_res = await handle_track_job_application(
        uid,
        {
            "action": "submit",
            "company": "Google",
            "role": "Software Engineer Intern",
            "job_url": "https://careers.google.com/jobs/123",
            "user_confirmed": False,
        },
        ctx,
    )
    assert unapproved_res["success"] is False
    assert unapproved_res["error"] == "ACTION_GATED"
    assert unapproved_res["requires_confirmation"] is True
    assert unapproved_res["status"] == "requires_user_approval"

    # Attempt to contact employer WITHOUT confirmation
    unapproved_contact = await handle_track_job_application(
        uid,
        {
            "action": "contact_employer",
            "company": "Google",
            "role": "Software Engineer Intern",
            "user_confirmed": False,
        },
        ctx,
    )
    assert unapproved_contact["success"] is False
    assert unapproved_contact["error"] == "ACTION_GATED"
    assert unapproved_contact["requires_confirmation"] is True

    # Attempt to submit WITH explicit confirmation
    approved_res = await handle_track_job_application(
        uid,
        {
            "action": "submit",
            "company": "Google",
            "role": "Software Engineer Intern",
            "job_url": "https://careers.google.com/jobs/123",
            "user_confirmed": True,
        },
        ctx,
    )
    assert approved_res["success"] is True
    assert approved_res["status"] == "submitted_with_approval"


# ============================================================================
# 4. MESSAGE DRAFTING & STYLE ADAPTATION
# ============================================================================

@pytest.mark.asyncio
async def test_message_drafting_adapts_to_stored_communication_style(study_user):
    """Message drafting adapts tone based on communication style preference in memory."""
    uid = study_user["id"]

    # Default casual tone
    casual_draft = await draft_whatsapp_reply(
        user_id=uid,
        contact_name="Sarah",
        instruction="confirming attendance for tomorrow",
    )
    assert casual_draft["success"] is True
    assert casual_draft["requires_confirmation"] is True
    assert "Hey Sarah" in casual_draft["draft_text"] or "Sounds great" in casual_draft["draft_text"]

    # Store preference for formal tone
    db.add_fact(
        user_id=uid,
        fact_text="Prefers formal and professional communication style in messages",
        category="preference",
        fact_type="preference",
        source="user_explicit",
        confidence=100,
    )

    # Formal draft
    formal_draft = await draft_whatsapp_reply(
        user_id=uid,
        contact_name="Professor Smith",
        instruction="confirming meeting tomorrow",
    )
    assert formal_draft["success"] is True
    assert formal_draft["requires_confirmation"] is True
    assert "Dear Professor Smith" in formal_draft["draft_text"]
