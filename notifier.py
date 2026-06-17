"""
GlitzTracker notifier — sends alerts via SMS (Twilio), Telegram, and email.
All three can be enabled simultaneously per user.
"""
import os
import logging

log = logging.getLogger("glitztracker.notify")

TWILIO_SID      = os.environ.get("TWILIO_ACCOUNT_SID","").strip()
TWILIO_TOKEN    = os.environ.get("TWILIO_AUTH_TOKEN","").strip()
TWILIO_FROM     = os.environ.get("TWILIO_PHONE_NUMBER","").strip()   # e.g. +18175551234
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
SENDGRID_KEY    = os.environ.get("SENDGRID_API_KEY","").strip()
FROM_EMAIL      = os.environ.get("FROM_EMAIL","alerts@glitztracker.com").strip()


def send_sms(to_number: str, message: str) -> bool:
    """Send SMS via Twilio. to_number must be E.164 e.g. +19725551234."""
    if not (TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM):
        log.warning("Twilio not configured — skipping SMS.")
        return False
    if not to_number:
        return False
    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        # SMS has 160-char limit per segment — Twilio auto-splits, but keep it tight
        msg = client.messages.create(
            body=message[:1600],
            from_=TWILIO_FROM,
            to=to_number,
        )
        log.info("SMS sent to %s (sid: %s)", to_number, msg.sid)
        return True
    except Exception as e:
        log.error("SMS send failed to %s: %s", to_number, e)
        return False


def send_telegram(chat_id: str, message: str) -> bool:
    if not (TELEGRAM_TOKEN and chat_id):
        return False
    try:
        import requests
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=30,
        )
        ok = r.status_code == 200
        if not ok:
            log.error("Telegram failed: %s %s", r.status_code, r.text[:200])
        return ok
    except Exception as e:
        log.error("Telegram send failed: %s", e)
        return False


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send via SendGrid if configured, else log (stub for now)."""
    if not (SENDGRID_KEY and to_email):
        log.info("EMAIL (no SendGrid key) → %s: %s", to_email, subject)
        return True   # don't fail the alert chain
    try:
        import requests
        r = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {SENDGRID_KEY}",
                     "Content-Type": "application/json"},
            json={
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": FROM_EMAIL, "name": "GlitzTracker"},
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            },
            timeout=30,
        )
        ok = r.status_code in (200, 202)
        if not ok:
            log.error("SendGrid failed: %s %s", r.status_code, r.text[:200])
        return ok
    except Exception as e:
        log.error("Email send failed: %s", e)
        return False


def notify_user(user, message: str, subject: str = "GlitzTracker Alert") -> bool:
    """
    Send to all enabled channels for a user.
    Returns True if at least one channel succeeded.
    """
    sent = False

    if user.notify_telegram and user.telegram_chat_id:
        sent = send_telegram(user.telegram_chat_id, message) or sent

    if user.notify_sms and user.phone_number and user.phone_verified:
        # SMS messages should be concise — strip to essentials
        sms_body = _sms_trim(message)
        sent = send_sms(user.phone_number, sms_body) or sent

    if user.notify_email:
        sent = send_email(user.effective_email, subject, message) or sent

    if not user.any_notify_enabled:
        log.warning("User %d has no notification channels enabled.", user.id)

    return sent


def _sms_trim(message: str, limit: int = 480) -> str:
    """Trim a message to fit comfortably in 3 SMS segments."""
    if len(message) <= limit:
        return message
    return message[:limit - 3] + "..."


def send_verification_sms(to_number: str, code: str) -> bool:
    """Send a 6-digit verification code to confirm a phone number."""
    body = f"GlitzTracker verification code: {code}\nExpires in 10 minutes."
    return send_sms(to_number, body)
