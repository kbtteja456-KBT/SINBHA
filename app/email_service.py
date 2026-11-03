"""
SINBHA Email Service (Step 17)
Handles transactional emails and security alerts:
- Email verification links (expires in 24 hours)
- One-time password reset links (expires in 30 minutes)
- "Password was changed" alert with report link
- Security alerts for:
  - New device pairing requests
  - Disconnect All / Revoke all sessions
  - New login from a new device
  - First trusted device email confirmation link (expires in 15 minutes)

Supports:
- Gmail SMTP (smtp.gmail.com:587 with STARTTLS + App Password)
- In-memory outbox for testing / offline verification inspection
- Safe fallback when credentials are not yet configured in .env
"""

import os
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

# In-memory outbox for testing and inspection
_outbox: List[Dict[str, Any]] = []

def get_outbox() -> List[Dict[str, Any]]:
    """Returns all sent emails (useful for testing and verification)."""
    return list(_outbox)

def clear_outbox():
    """Clears the in-memory outbox."""
    global _outbox
    _outbox.clear()

def get_base_url() -> str:
    """Returns application base URL (e.g. http://localhost:8080 or production domain)."""
    url = os.getenv("APP_URL") or os.getenv("BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "https://sinbha-backend.onrender.com"
    # If running on Render or in production, ensure external accessible URL is used
    if ("localhost" in url or "127.0.0.1" in url) and (os.getenv("RENDER") or os.getenv("RENDER_EXTERNAL_URL") or os.getenv("ENV") == "production"):
        url = os.getenv("RENDER_EXTERNAL_URL") or "https://sinbha-backend.onrender.com"
    return url.rstrip("/")

def send_email_sync(
    to_email: str,
    subject: str,
    text_content: str,
    html_content: Optional[str] = None
) -> bool:
    """
    Sends an email synchronously via SMTP or records to outbox in dev/test.
    """
    to_email = to_email.strip().lower()
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587").strip())
    # Provide reliable fallback if Render environment variables were not explicitly entered
    smtp_user = os.getenv("SMTP_USER", "").strip() or "kbtteja456@gmail.com"
    smtp_pass = (os.getenv("SMTP_PASS", "").strip() or "ecfa wjgk kbin grfz").replace(" ", "")
    from_name = os.getenv("SMTP_FROM_NAME", "SINBHA Companion").strip()
    from_email = os.getenv("SMTP_FROM_EMAIL", smtp_user or "no-reply@sinbha.local").strip()

    email_record = {
        "to": to_email,
        "from": f"{from_name} <{from_email}>",
        "subject": subject,
        "text": text_content,
        "html": html_content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _outbox.append(email_record)

    # Step 1C Item 2: In tests or offline dev mode, NEVER use real SMTP credentials
    import sys
    is_test = "pytest" in sys.modules or bool(os.getenv("PYTEST_CURRENT_TEST")) or os.getenv("MOCK_EMAIL", "").lower() == "true"
    if is_test or not smtp_user or not smtp_pass:
        print(f"[EMAIL SERVICE - DEV/OFFLINE] To: {to_email} | Subject: '{subject}' | Recorded to outbox.")
        return True

    # Real SMTP send via configured provider (e.g. Gmail with App Password)
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to_email

        # Attach text part
        part1 = MIMEText(text_content, "plain", "utf-8")
        msg.attach(part1)

        # Attach html part if provided
        if html_content:
            part2 = MIMEText(html_content, "html", "utf-8")
            msg.attach(part2)

        sent = False
        try:
            if smtp_port == 465:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=12) as server:
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                    sent = True
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                    sent = True
        except Exception as e_initial:
            # If port 587 timed out or blocked, try port 465 SSL fallback
            if smtp_port != 465:
                try:
                    with smtplib.SMTP_SSL(smtp_host, 465, timeout=12) as server:
                        server.login(smtp_user, smtp_pass)
                        server.send_message(msg)
                        sent = True
                except Exception:
                    raise e_initial
            else:
                raise e_initial

        if sent:
            print(f"[EMAIL SERVICE - REAL SMTP] Successfully sent email to {to_email}: '{subject}'")
            return True
        return False
    except Exception as e:
        print(f"[EMAIL SERVICE ERROR] Failed to send email to {to_email}: {e}")
        return False

async def send_email_async(
    to_email: str,
    subject: str,
    text_content: str,
    html_content: Optional[str] = None
) -> bool:
    """Non-blocking email dispatch."""
    return await asyncio.to_thread(send_email_sync, to_email, subject, text_content, html_content)


# -------------------------------------------------------------
# Template Dispatchers
# -------------------------------------------------------------

def send_verification_email(to_email: str, token: str, base_url: Optional[str] = None) -> bool:
    """Requirement 2: Verification email with expiring link."""
    base = (base_url or get_base_url()).rstrip("/")
    verify_link = f"{base}/verify-email?token={token}"
    api_link = f"{base}/api/auth/verify-email?token={token}"

    subject = "Verify your SINBHA account"
    text = (
        f"Welcome to SINBHA! 🌸\n\n"
        f"Please verify your email address to unlock device pairing and remote companion features.\n\n"
        f"Verification Link (valid for 24 hours):\n"
        f"{verify_link}\n\n"
        f"Direct API confirmation link:\n"
        f"{api_link}\n\n"
        f"If you did not create this account, you can safely ignore this email."
    )
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 580px; margin: 0 auto; padding: 24px; border: 1px solid #fed7aa; border-radius: 12px; background: #fffaf5;">
        <h2 style="color: #ea580c; margin-top: 0;">🌸 Welcome to SINBHA</h2>
        <p style="font-size: 15px; color: #431407; line-height: 1.5;">
            Thank you for creating an account. Please verify your email address to enable device pairing and remote companion actions.
        </p>
        <div style="margin: 28px 0; text-align: center;">
            <a href="{verify_link}" style="display: inline-block; background: #f97316; color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                Verify My Email
            </a>
        </div>
        <p style="font-size: 13px; color: #78350f;">
            This link is valid for <strong>24 hours</strong>.<br/>
            If the button doesn't work, copy and paste this URL into your browser:<br/>
            <a href="{verify_link}" style="color: #ea580c; word-break: break-all;">{verify_link}</a>
        </p>
        <hr style="border: none; border-top: 1px solid #ffedd5; margin: 24px 0;" />
        <p style="font-size: 12px; color: #9a3412;">
            If you did not sign up for SINBHA, you can safely disregard this message.
        </p>
    </div>
    """
    return send_email_sync(to_email, subject, text, html)


def send_password_reset_email(to_email: str, token: str, base_url: Optional[str] = None) -> bool:
    """Requirement 3: One-time password reset link expiring in 30 minutes."""
    base = (base_url or get_base_url()).rstrip("/")
    reset_link = f"{base}/reset-password?token={token}"

    subject = "Reset your SINBHA password"
    text = (
        f"We received a request to reset your SINBHA password.\n\n"
        f"Click the link below to set a new password. This link is valid for 30 minutes:\n"
        f"{reset_link}\n\n"
        f"If you did not request a password reset, please ignore this email. Your current password remains secure."
    )
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 580px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background: #ffffff;">
        <h2 style="color: #0f172a; margin-top: 0;">🔒 Reset Your Password</h2>
        <p style="font-size: 15px; color: #334155; line-height: 1.5;">
            We received a request to reset your SINBHA account password. Click the button below to choose a new password:
        </p>
        <div style="margin: 28px 0; text-align: center;">
            <a href="{reset_link}" style="display: inline-block; background: #2563eb; color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                Reset Password
            </a>
        </div>
        <p style="font-size: 13px; color: #64748b;">
            This link is one-time use and expires in <strong>30 minutes</strong>.<br/>
            If you did not request this, you can safely ignore this message. Your password will not change.
        </p>
        <p style="font-size: 12px; color: #94a3b8; word-break: break-all;">
            URL: {reset_link}
        </p>
    </div>
    """
    return send_email_sync(to_email, subject, text, html)


def send_password_changed_notification(to_email: str, client_ip: str = "Unknown", base_url: Optional[str] = None) -> bool:
    """Requirement 4: Notification after password change with security report link."""
    base = (base_url or get_base_url()).rstrip("/")
    report_link = f"{base}/security/report?action=unauthorized_password_change"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    subject = "Security Alert: Your SINBHA password was changed"
    text = (
        f"Your SINBHA password was successfully changed at {now_str} (IP: {client_ip}).\n\n"
        f"All active login sessions and device tokens have been invalidated for security.\n\n"
        f"If you made this change, no further action is required.\n\n"
        f"If you did NOT make this change, please report it immediately:\n"
        f"{report_link}\n"
        f"Or contact support at security@sinbha.local"
    )
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 580px; margin: 0 auto; padding: 24px; border: 1px solid #fecaca; border-radius: 12px; background: #fffafb;">
        <h2 style="color: #dc2626; margin-top: 0;">⚠️ Your Password Was Changed</h2>
        <p style="font-size: 15px; color: #1f2937; line-height: 1.5;">
            The password for your SINBHA account was changed on <strong>{now_str}</strong> from IP <code>{client_ip}</code>.
        </p>
        <p style="font-size: 14px; color: #4b5563;">
            All previous sessions and device tokens have been automatically revoked. Any paired devices must log in again with the new password.
        </p>
        <div style="margin: 24px 0; padding: 16px; background: #fee2e2; border-radius: 8px;">
            <p style="margin: 0; font-size: 14px; color: #991b1b; font-weight: 600;">
                Did not request this change?
            </p>
            <p style="margin: 8px 0 0; font-size: 13px; color: #b91c1c;">
                Report unauthorized access immediately: <br/>
                <a href="{report_link}" style="color: #b91c1c; font-weight: bold;">Report Unauthorized Change</a>
            </p>
        </div>
    </div>
    """
    return send_email_sync(to_email, subject, text, html)


def send_first_device_confirmation_email(
    to_email: str,
    device_name: str,
    platform: str,
    token: str,
    base_url: Optional[str] = None
) -> bool:
    """Requirement 6: First trusted device requires password AND email confirmation link."""
    base = (base_url or get_base_url()).rstrip("/")
    confirm_link = f"{base}/api/devices/confirm-first-device?token={token}"

    subject = f"Authorize First Device: {device_name}"
    text = (
        f"A request was made to trust your first device:\n"
        f"Device: {device_name} ({platform})\n\n"
        f"To confirm and trust this device, click the authorization link below (valid for 15 minutes):\n"
        f"{confirm_link}\n\n"
        f"If you did not initiate this request, do not click the link."
    )
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 580px; margin: 0 auto; padding: 24px; border: 1px solid #fed7aa; border-radius: 12px; background: #ffffff;">
        <h2 style="color: #c2410c; margin-top: 0;">📱 Authorize First Trusted Device</h2>
        <p style="font-size: 15px; color: #374151; line-height: 1.5;">
            Your account requires email confirmation to trust your first companion device:
        </p>
        <ul style="font-size: 14px; color: #4b5563;">
            <li><strong>Device Name:</strong> {device_name}</li>
            <li><strong>Platform:</strong> {platform}</li>
        </ul>
        <div style="margin: 28px 0; text-align: center;">
            <a href="{confirm_link}" style="display: inline-block; background: #ea580c; color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                Trust This Device
            </a>
        </div>
        <p style="font-size: 13px; color: #6b7280;">
            This link is valid for <strong>15 minutes</strong>. If you did not request this, disregard this email.
        </p>
    </div>
    """
    return send_email_sync(to_email, subject, text, html)


def send_security_alert_pairing_request(
    to_email: str,
    device_name: str,
    platform: str,
    ip_address: str = "Unknown",
    pairing_code: Optional[str] = None
) -> bool:
    """Requirement 5: Email alert for new device pairing request."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = f"Security Alert: New device pairing request ({device_name})"
    code_text = f"Pairing Code: {pairing_code}\n" if pairing_code else ""
    text = (
        f"A new device is requesting to pair with your SINBHA account:\n"
        f"Device: {device_name} ({platform})\n"
        f"IP Address: {ip_address}\n"
        f"Time: {now_str}\n"
        f"{code_text}\n"
        f"If this was not you, disconnect all devices in your account settings."
    )
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 580px; margin: 0 auto; padding: 24px; border: 1px solid #fed7aa; border-radius: 12px; background: #fffaf5;">
        <h2 style="color: #d97706; margin-top: 0;">🔔 New Device Pairing Request</h2>
        <p style="font-size: 14px; color: #451a03;">
            A pairing request was initiated for your companion network:
        </p>
        <ul style="font-size: 14px; color: #78350f;">
            <li><strong>Device:</strong> {device_name} ({platform})</li>
            <li><strong>IP Address:</strong> {ip_address}</li>
            <li><strong>Time:</strong> {now_str}</li>
            {f'<li><strong>Pairing Code:</strong> <code>{pairing_code}</code></li>' if pairing_code else ''}
        </ul>
        <p style="font-size: 12px; color: #92400e;">
            If you did not initiate this, navigate to Settings > Security > Disconnect All Devices.
        </p>
    </div>
    """
    return send_email_sync(to_email, subject, text, html)


def send_security_alert_disconnect_all(
    to_email: str,
    count: int,
    ip_address: str = "Unknown"
) -> bool:
    """Requirement 5: Email alert for Disconnect All."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = "Security Alert: All devices disconnected"
    text = (
        f"Security Notice:\n"
        f"All {count} paired devices and sessions have been disconnected from your account at {now_str} (IP: {ip_address}).\n\n"
        f"If you did not perform this action, please reset your password immediately."
    )
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 580px; margin: 0 auto; padding: 24px; border: 1px solid #cbd5e1; border-radius: 12px; background: #f8fafc;">
        <h2 style="color: #334155; margin-top: 0;">🔌 All Devices Disconnected</h2>
        <p style="font-size: 14px; color: #475569;">
            All <strong>{count}</strong> devices and active sessions were revoked from your account on {now_str} (IP: {ip_address}).
        </p>
        <p style="font-size: 12px; color: #64748b;">
            To re-pair your companion devices, log in from your primary laptop or phone.
        </p>
    </div>
    """
    return send_email_sync(to_email, subject, text, html)


def send_security_alert_new_login(
    to_email: str,
    device_name: str,
    platform: str,
    ip_address: str = "Unknown"
) -> bool:
    """Requirement 5: Email alert for new login from a new device."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = f"Security Notice: New login from {device_name}"
    text = (
        f"A new login to your SINBHA account was detected:\n"
        f"Device: {device_name} ({platform})\n"
        f"IP Address: {ip_address}\n"
        f"Time: {now_str}\n\n"
        f"If this was you, you can safely ignore this email.\n"
        f"If you don't recognize this activity, reset your password immediately."
    )
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 580px; margin: 0 auto; padding: 24px; border: 1px solid #bfdbfe; border-radius: 12px; background: #eff6ff;">
        <h2 style="color: #1d4ed8; margin-top: 0;">ℹ️ New Login Detected</h2>
        <p style="font-size: 14px; color: #1e3a8a;">
            A login from a new device was recorded on your account:
        </p>
        <ul style="font-size: 14px; color: #1e40af;">
            <li><strong>Device:</strong> {device_name} ({platform})</li>
            <li><strong>IP Address:</strong> {ip_address}</li>
            <li><strong>Time:</strong> {now_str}</li>
        </ul>
        <p style="font-size: 12px; color: #3b82f6;">
            If this was not you, please reset your password immediately.
        </p>
    </div>
    """
    return send_email_sync(to_email, subject, text, html)

