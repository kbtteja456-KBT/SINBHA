"""
Step D3: Official Data Tools Tests
SINBHA Official Integrations Layer

Test suite covers:
1. YouTube Data API v3:
   - Channel stats (subscribers, video count, view count, latest videos).
   - Answer format includes channel link, numbers, time checked, and subscriber rounding disclaimer.
   - Missing API key error handling.
   - Channel not found error handling.
2. Gmail Tool (Read & Draft Only):
   - Smallest scopes verification (readonly, compose).
   - Google app verification rules and testing limits guide.
   - Reading emails with untrusted content detection (phishing, prompt injection).
   - Drafting emails with Action Gating (requires explicit user confirmation).
   - Safe typing enforcement (blocks passwords, OTPs, card numbers).
   - Sending approved email.
3. Privacy Disclosure Note:
   - Zero server database storage, ephemeral memory processing, zero automatic sending.
4. Agent Tool Handlers Integration.
"""

import pytest
import asyncio
import time
from unittest.mock import patch, MagicMock

from app.official_data_tools import (
    fetch_youtube_channel_stats,
    get_youtube_api_key,
    generate_google_oauth_url,
    get_google_testing_guide,
    fetch_recent_emails,
    draft_email,
    send_approved_email,
    get_official_data_privacy_note,
    GMAIL_SCOPES,
)
from app.agent_tools import (
    handle_get_youtube_channel_stats,
    handle_read_gmail_messages,
    handle_draft_gmail_message,
    handle_get_google_testing_info,
)
from app import database as db


@pytest.fixture
def test_user():
    email = f"d3_tester_{int(time.time()*1000)}@sinbha.local"
    user = db.create_user(email, "hashed_pw", "D3 Tester", "UTC")
    u_id = user["id"] if isinstance(user, dict) else user
    return {"id": u_id, "email": email}


# ============================================================================
# 1. YOUTUBE DATA API V3
# ============================================================================

@pytest.mark.asyncio
async def test_youtube_missing_api_key():
    """Returns clear error if server does not have YOUTUBE_API_KEY configured."""
    with patch("app.official_data_tools.get_youtube_api_key", return_value=None):
        res = await fetch_youtube_channel_stats("GoogleDeepMind")
        assert res["success"] is False
        assert res["error"] == "MISSING_API_KEY"
        assert "YOUTUBE_API_KEY" in res["message"]


@pytest.mark.asyncio
async def test_youtube_channel_stats_format():
    """
    Channel statistics must answer with numbers, channel link, time checked,
    and the explicit subscriber rounding disclaimer.
    """
    def mock_yt(query, time_human, time_iso):
        return {
            "success": True,
            "channel_title": "Google DeepMind",
            "channel_url": "https://www.youtube.com/@GoogleDeepMind",
            "channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
            "subscribers": 542000,
            "subscribers_formatted": "542,000",
            "subscriber_rounding_notice": "Note: YouTube rounds subscriber counts for privacy, so numbers may be approximate.",
            "video_count": 310,
            "view_count": 28400000,
            "latest_videos": [
                {"title": "Gemini 2.5 Overview", "video_url": "https://www.youtube.com/watch?v=abc12345", "published_at": "2026-10-20"},
                {"title": "Agentic Coding Frontier", "video_url": "https://www.youtube.com/watch?v=def67890", "published_at": "2026-10-15"},
            ],
            "time_checked": time_human,
            "time_checked_iso": time_iso,
            "summary": (
                "**Google DeepMind** (https://www.youtube.com/@GoogleDeepMind)\n"
                "• **Subscribers:** 542,000 *(Note: YouTube rounds subscriber counts for privacy)*\n"
                f"• **Checked at:** {time_human}"
            )
        }

    res = await fetch_youtube_channel_stats("@GoogleDeepMind", mock_client=mock_yt)
    assert res["success"] is True
    assert res["channel_title"] == "Google DeepMind"
    assert "https://www.youtube.com/@GoogleDeepMind" in res["channel_url"]
    assert res["subscribers"] == 542000
    assert res["video_count"] == 310
    assert len(res["latest_videos"]) == 2
    assert "Note: YouTube rounds subscriber counts for privacy" in res["subscriber_rounding_notice"]
    assert res["time_checked"] is not None


# ============================================================================
# 2. GMAIL SMALLEST SCOPES & GOOGLE APP VERIFICATION RULES
# ============================================================================

def test_gmail_uses_smallest_scopes():
    """Smallest scopes: only readonly and compose drafts."""
    assert len(GMAIL_SCOPES) == 2
    assert "https://www.googleapis.com/auth/gmail.readonly" in GMAIL_SCOPES
    assert "https://www.googleapis.com/auth/gmail.compose" in GMAIL_SCOPES
    # Strictly ensure full mail.google.com scope is NOT requested
    assert "https://mail.google.com/" not in GMAIL_SCOPES


def test_google_testing_guide():
    """Google testing guide provides exact rules, test user limits, and bypass steps."""
    guide = get_google_testing_guide()
    assert guide["publishing_status"] == "Testing"
    rules_text = " ".join(guide["verification_rules"])
    assert "Test users" in rules_text
    assert "100" in rules_text  # 100 test user limit
    assert "7 days" in rules_text  # 7-day token expiration
    assert "Google hasn't verified this app" in rules_text
    assert "Advanced" in rules_text


def test_generate_google_oauth_url(test_user):
    """OAuth URL includes smallest scopes and user state."""
    with patch("app.official_data_tools.get_google_oauth_config", return_value={
        "client_id": "test_client_id_123.apps.googleusercontent.com",
        "client_secret": "test_secret",
        "redirect_uri": "http://localhost:8080/api/auth/google/callback",
        "scopes": GMAIL_SCOPES,
    }):
        res = generate_google_oauth_url(test_user["id"])
        assert res["success"] is True
        assert "accounts.google.com/o/oauth2/v2/auth" in res["auth_url"]
        assert "gmail.readonly" in res["auth_url"]
        assert "gmail.compose" in res["auth_url"]


# ============================================================================
# 3. UNTRUSTED EMAIL DATA DEFENSE
# ============================================================================

@pytest.mark.asyncio
async def test_read_emails_untrusted_content_detected(test_user):
    """Incoming emails asking for OTPs or credentials must be flagged as untrusted."""
    def mock_email_feed(uid, q, limit):
        return {
            "success": True,
            "count": 2,
            "emails": [
                {
                    "id": "msg_001",
                    "from": "Phisher <attacker@evil.com>",
                    "subject": "Urgent: Send your OTP to restore account",
                    "snippet": "We noticed suspicious activity. Please send your OTP immediately.",
                    "is_suspicious": True,
                    "security_warning": "⚠️ Suspicious instructions detected",
                    "reasons": ["Requesting OTP, password, or security credentials"]
                },
                {
                    "id": "msg_002",
                    "from": "Newsletter <news@tech.com>",
                    "subject": "Weekly Tech Highlights",
                    "snippet": "Here are the top stories in agentic computing this week.",
                    "is_suspicious": False,
                    "security_warning": None,
                    "reasons": []
                }
            ],
            "has_suspicious_content": True,
            "warning_notice": "⚠️ Security Notice: An incoming email contains suspicious requests.",
            "untrusted_data_notice": "Email content is untrusted data."
        }

    res = await fetch_recent_emails(
        user_id=test_user["id"],
        mock_provider=mock_email_feed
    )

    assert res["success"] is True
    assert res["count"] == 2
    assert res["has_suspicious_content"] is True
    assert res["emails"][0]["is_suspicious"] is True
    assert res["emails"][1]["is_suspicious"] is False


# ============================================================================
# 4. ACTION GATING ON SENDING & SECRET PROTECTION
# ============================================================================

@pytest.mark.asyncio
async def test_draft_email_requires_user_confirmation(test_user):
    """Draft email strictly requires user confirmation card showing recipient, subject, and text."""
    res = await draft_email(
        user_id=test_user["id"],
        to="colleague@example.com",
        subject="Sprint Review Agenda",
        body="Hi Team, here is the sprint review agenda for tomorrow at 10am.",
    )

    assert res["success"] is True
    assert res["status"] == "draft_created"
    assert res["needs_user_confirmation"] is True
    assert res["requires_confirmation"] is True
    assert res["to"] == "colleague@example.com"
    assert res["subject"] == "Sprint Review Agenda"
    assert "tomorrow at 10am" in res["body"]
    assert "Send email to colleague@example.com" in res["confirmation_template"]


@pytest.mark.asyncio
async def test_draft_email_blocks_secret_typing(test_user):
    """Refuses to draft emails containing passwords, OTPs, or credit cards."""
    res = await draft_email(
        user_id=test_user["id"],
        to="friend@example.com",
        subject="Secrets",
        body="My account password is Secret123!",
    )
    assert res["success"] is False
    assert res["error"] == "SECRET_TYPING_REFUSED"


@pytest.mark.asyncio
async def test_send_approved_email(test_user):
    """Sends email only after user approval."""
    def mock_sender(to, subject, body, draft_id):
        return {"success": True, "status": "sent", "message": f"Email delivered to {to}"}

    res = await send_approved_email(
        user_id=test_user["id"],
        to="partner@example.com",
        subject="Project Agreement",
        body="Agreed on the project terms.",
        mock_provider=mock_sender,
    )
    assert res["success"] is True
    assert "Email delivered to partner@example.com" in res["message"]


# ============================================================================
# 5. PRIVACY DISCLOSURE
# ============================================================================

def test_official_data_privacy_note():
    """Privacy disclosure must state zero server database storage and zero automatic sending."""
    note = get_official_data_privacy_note()
    assert note["zero_server_storage"] is True
    assert note["zero_automatic_sending"] is True
    assert "NEVER stored in database tables" in note["gmail_privacy"]
    assert "YouTube channel statistics are publicly available" in note["youtube_privacy"]


# ============================================================================
# 6. AGENT TOOL HANDLERS INTEGRATION
# ============================================================================

@pytest.mark.asyncio
async def test_agent_tool_handlers_d3_integration(test_user):
    """Verifies tool handler integration for official data tools."""
    ctx = {"db": db, "relay_manager": None}

    # 1. Google Testing Info
    res_guide = await handle_get_google_testing_info(test_user["id"], {}, ctx)
    assert res_guide["publishing_status"] == "Testing"

    # 2. Draft Gmail
    res_draft = await handle_draft_gmail_message(
        user_id=test_user["id"],
        args={"to": "client@corp.com", "subject": "Meeting", "body": "Let's meet at 4."},
        ctx=ctx
    )
    assert res_draft["success"] is True
    assert res_draft["needs_user_confirmation"] is True
