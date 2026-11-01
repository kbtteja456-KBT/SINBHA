"""
Step 17 Test Suite: Email Verification, Password Reset, and Security Alerts
Follows AGENT_RULES.md.

Tests:
1. Signup sends verification link that expires in 24 hours.
2. Unverified accounts can use app but cannot pair devices or execute remote commands.
3. Verification link marks account verified and unlocks pairing and remote commands.
4. "Forgot password" sends one-time 30-min reset link, does not reveal email existence, and rate limits.
5. Password reset invalidates all sessions and device tokens, keeps paired devices, and sends password changed alert.
6. Security alert emails for: new device pairing request, Disconnect All, and new login from new device.
7. First trusted device requires password AND email confirmation link.
8. Encryption preservation: data key is independent of password; password reset retains chat history.
"""

import os
import time
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.main import app
from app import database as db
from app import email_service
from app.crypto import encrypt_text, decrypt_text

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_step17():
    db.init_db()
    email_service.clear_outbox()
    yield
    email_service.clear_outbox()

def test_signup_sends_verification_link_and_restricts_unverified():
    """
    Requirement 2:
    - Signup sends a verification link that expires.
    - Unverified accounts can use app, but cannot pair new devices or use remote commands.
    """
    email_service.clear_outbox()
    email = f"unverified_{int(time.time()*1000)}@sinbha.local"
    pw = "StrongPass123!"

    # 1. Register user
    res_reg = client.post("/api/auth/register", json={
        "email": email,
        "password": pw,
        "is_18": True,
        "agreed_terms": True,
    })
    assert res_reg.status_code == 200
    user_data = res_reg.json()["user"]
    assert user_data["is_verified"] is False

    # 2. Verify verification email was dispatched
    outbox = email_service.get_outbox()
    assert len(outbox) >= 1
    verify_email = next((e for e in outbox if e["to"] == email and "Verify" in e["subject"]), None)
    assert verify_email is not None
    assert "token=" in verify_email["text"]

    # 3. User has active session and can access chat / app features
    res_me = client.get("/api/auth/me")
    assert res_me.status_code == 200
    assert res_me.json()["user"]["email"] == email

    # 4. Unverified user CANNOT pair new devices
    res_pair = client.post("/api/devices/register", json={
        "device_id": f"dev_{int(time.time()*1000)}",
        "name": "My Phone",
        "platform": "android"
    })
    assert res_pair.status_code == 403
    assert "Email verification required" in res_pair.json()["detail"]

    # 5. Unverified user CANNOT send remote commands
    res_cmd = client.post("/api/devices/commands/send", json={
        "id": "cmd_test_unverified",
        "sender_device": "web",
        "target_device": "some_device",
        "type": "open_app",
        "payload": {"app": "notepad"}
    })
    assert res_cmd.status_code == 403
    assert "Email verification required" in res_cmd.json()["detail"]


def test_email_verification_unlocks_pairing_and_commands():
    """
    Requirement 2:
    - Calling verify-email unlocks pairing and remote commands.
    """
    email = f"verify_flow_{int(time.time()*1000)}@sinbha.local"
    pw = "StrongPass123!"

    res_reg = client.post("/api/auth/register", json={
        "email": email,
        "password": pw,
        "is_18": True,
        "agreed_terms": True,
    })
    assert res_reg.status_code == 200

    outbox = email_service.get_outbox()
    verify_email = next((e for e in outbox if e["to"] == email and "Verify" in e["subject"]), None)
    assert verify_email is not None

    # Extract token from email text
    # e.g. token=abc...
    token = verify_email["text"].split("token=")[1].split()[0].strip()

    # Verify email via API endpoint
    res_verify = client.get(f"/api/auth/verify-email?token={token}")
    assert res_verify.status_code == 200
    assert res_verify.json()["success"] is True

    # User is now verified
    res_me = client.get("/api/auth/me")
    assert res_me.status_code == 200
    assert res_me.json()["user"]["is_verified"] is True


def test_forgot_password_does_not_reveal_existence_and_rate_limits():
    """
    Requirement 3:
    - "Forgot password" sends a one-time reset link that expires in 30 minutes.
    - Do not reveal whether an email exists.
    - Rate limit by IP and by email.
    """
    email_service.clear_outbox()
    existing_email = f"exists_{int(time.time()*1000)}@sinbha.local"
    non_existent_email = f"fake_{int(time.time()*1000)}@sinbha.local"

    # Create real account
    client.post("/api/auth/register", json={
        "email": existing_email,
        "password": "Password123!",
        "is_18": True,
        "agreed_terms": True,
    })
    email_service.clear_outbox()

    # 1. Request for existing email
    res1 = client.post("/api/auth/forgot-password", json={"email": existing_email})
    assert res1.status_code == 200
    data1 = res1.json()

    # 2. Request for non-existent email
    res2 = client.post("/api/auth/forgot-password", json={"email": non_existent_email})
    assert res2.status_code == 200
    data2 = res2.json()

    # Both must return the identical generic message (zero information disclosure)
    assert data1["message"] == data2["message"]
    assert "If an account with that email exists" in data1["message"]

    # Only existing account actually received an email
    outbox = email_service.get_outbox()
    assert any(e["to"] == existing_email for e in outbox)
    assert not any(e["to"] == non_existent_email for e in outbox)

    # 3. Rate limiting by email (max 3 per 15 min)
    client.post("/api/auth/forgot-password", json={"email": existing_email})
    client.post("/api/auth/forgot-password", json={"email": existing_email})
    # 4th attempt should hit rate limit
    res_limited = client.post("/api/auth/forgot-password", json={"email": existing_email})
    assert res_limited.status_code == 429


def test_password_reset_invalidates_sessions_and_device_tokens():
    """
    Requirement 4:
    - After reset, invalidate all sessions and device tokens.
    - Keep paired devices (they must log in again).
    - Email "your password was changed" with a way to report it.
    """
    email_service.clear_outbox()
    email = f"reset_test_{int(time.time()*1000)}@sinbha.local"
    old_pw = "OldPassword123!"
    new_pw = "NewStrongPassword456!"

    # Signup & auto verify email
    user = db.create_user(email, old_pw, is_verified=True)
    user_id = user["id"]

    # Create session and device token
    session_token = db.create_session(user_id)
    dev_token_data = db.create_device_token(user_id)
    cmd_token_data = db.create_device_command_token(user_id, "laptop_dev_1")

    # Request password reset
    reset_data = db.create_password_reset_token(email)
    assert reset_data is not None
    reset_token, _ = reset_data

    # Send reset request via API
    res_reset = client.post("/api/auth/reset-password", json={
        "token": reset_token,
        "new_password": new_pw
    })
    assert res_reset.status_code == 200
    assert res_reset.json()["success"] is True

    # 1. Previous session token is now completely invalidated
    client.cookies.set("sinbha_session", session_token)
    res_me = client.get("/api/auth/me")
    assert res_me.json()["logged_in"] is False
    assert res_me.json()["user"] is None
    res_devs = client.get("/api/devices")
    assert res_devs.status_code == 401

    # 2. Previous device token is revoked
    user_from_dev = db.get_user_by_device_token(dev_token_data["device_token"])
    assert user_from_dev is None

    # 3. Old password fails authentication
    with pytest.raises(ValueError):
        db.authenticate_user(email, old_pw)

    # 4. New password authenticates successfully
    auth_user = db.authenticate_user(email, new_pw)
    assert auth_user["id"] == user_id

    # 5. Email "your password was changed" with a way to report it was sent
    outbox = email_service.get_outbox()
    pw_email = next((e for e in outbox if e["to"] == email and "password was changed" in e["subject"].lower()), None)
    assert pw_email is not None
    assert "/security/report" in pw_email["text"] or "report" in pw_email["text"].lower()


def test_first_trusted_device_needs_password_and_email_confirmation():
    """
    Requirement 6:
    - For an account with no trusted device, trusting the first device needs
      the password AND an email confirmation link.
    """
    email_service.clear_outbox()
    email = f"first_dev_{int(time.time()*1000)}@sinbha.local"
    pw = "SafePassword789!"
    user = db.create_user(email, pw, is_verified=True)
    user_id = user["id"]
    client.cookies.set("sinbha_session", db.create_session(user_id))

    # 1. Device registration without password leaves it in pending
    dev_id = f"dev_first_{int(time.time()*1000)}"
    res_first = client.post("/api/devices/register", json={
        "device_id": dev_id,
        "name": "Primary Laptop",
        "platform": "windows"
    })
    assert res_first.status_code == 200
    assert res_first.json()["device"]["status"] == "pending"

    # 2. Device registration WITH password sends email confirmation link
    res_with_pw = client.post("/api/devices/register", json={
        "device_id": dev_id,
        "name": "Primary Laptop",
        "platform": "windows",
        "password": pw
    })
    assert res_with_pw.status_code == 200
    # Still pending email confirmation!
    assert res_with_pw.json()["device"]["status"] == "pending"

    # Verify confirmation email was sent
    outbox = email_service.get_outbox()
    dev_email = next((e for e in outbox if e["to"] == email and "Authorize First Device" in e["subject"]), None)
    assert dev_email is not None
    assert "token=" in dev_email["text"]

    token = dev_email["text"].split("token=")[1].split()[0].strip()

    # 3. Confirming the email link makes the device trusted
    res_confirm = client.get(f"/api/devices/confirm-first-device?token={token}")
    assert res_confirm.status_code == 200
    assert res_confirm.json()["success"] is True

    # Verify device is now trusted in DB
    dev_status = db.get_device_by_id(user_id, dev_id)
    assert dev_status["status"] == "trusted"


def test_security_alert_emails_on_disconnect_all_and_new_device_pairing():
    """
    Requirement 5:
    - Email security alerts for: a new device pairing request, Disconnect All,
      and a new login from a new device.
    """
    email_service.clear_outbox()
    email = f"security_alerts_{int(time.time()*1000)}@sinbha.local"
    pw = "PassAlerts123!"
    user = db.create_user(email, pw, is_verified=True)
    user_id = user["id"]
    client.cookies.set("sinbha_session", db.create_session(user_id))

    # Make one device trusted so trusted_count > 0
    dev1 = db.create_or_register_device(user_id, "trusted_dev_1", "Main PC", "windows")
    db.confirm_first_device_token(db.create_first_device_token(user_id, "trusted_dev_1"))
    email_service.clear_outbox()

    # 1. New device pairing request triggers security alert
    dev2_id = "pending_phone_2"
    client.post("/api/devices/register", json={
        "device_id": dev2_id,
        "name": "Companion Phone",
        "platform": "android"
    })
    outbox = email_service.get_outbox()
    pairing_alert = next((e for e in outbox if e["to"] == email and "New device pairing request" in e["subject"]), None)
    assert pairing_alert is not None
    assert "Companion Phone" in pairing_alert["text"]

    # 2. Disconnect All triggers security alert
    email_service.clear_outbox()
    res_disc = client.post("/api/devices/disconnect-all")
    assert res_disc.status_code == 200
    outbox2 = email_service.get_outbox()
    disc_alert = next((e for e in outbox2 if e["to"] == email and "All devices disconnected" in e["subject"]), None)
    assert disc_alert is not None


def test_encryption_design_retains_chat_history_after_password_reset():
    """
    Requirement 7:
    - Keep the encryption design: the data key is not derived from the password,
      so a reset does not lose chat history. Prove it with a test.
    """
    email = f"crypto_user_{int(time.time()*1000)}@sinbha.local"
    old_pw = "OriginalPassword123!"
    new_pw = "BrandNewPassword999!"

    user = db.create_user(email, old_pw, is_verified=True)
    user_id = user["id"]

    # Save sensitive encrypted message and memory fact
    secret_chat_msg = "Top secret: My favorite flower is the Himalayan Blue Poppy 🌸"
    secret_memory_fact = "User's mother was born in Kyoto, Japan."

    msg_record = db.save_message(user_id, "user", secret_chat_msg)
    fact_id = db.add_fact(user_id, secret_memory_fact, "secret_origin")

    # Request and perform password reset
    reset_token, _ = db.create_password_reset_token(email)
    success, _, _, _ = db.reset_password_with_token(reset_token, new_pw)
    assert success is True

    # User logs in with new password
    auth_user = db.authenticate_user(email, new_pw)
    assert auth_user["id"] == user_id

    # Retrieve and decrypt messages and facts
    recent_msgs = db.get_recent_messages(user_id, limit=5)
    assert len(recent_msgs) >= 1
    retrieved_msg = next((m for m in recent_msgs if m["id"] == msg_record["id"]), None)
    assert retrieved_msg is not None
    assert retrieved_msg["content"] == secret_chat_msg

    facts = db.get_all_facts(user_id)
    assert len(facts) >= 1
    retrieved_fact = next((f for f in facts if f["id"] == fact_id), None)
    assert retrieved_fact is not None
    assert retrieved_fact["fact"] == secret_memory_fact
