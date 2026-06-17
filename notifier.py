"""
GlitzTracker notifier — SMS (Twilio), WhatsApp (Twilio), Telegram, Email (SendGrid).
All four can run simultaneously per user.
"""
import os
import logging

log = logging.getLogger("glitztracker.notify")

TWILIO_SID   = os.environ.get("TWILIO_ACCOUNT_SID","").strip()
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN","").strip()
TWILIO_FROM  = os.environ.get("TWILIO_PHONE_NUMBER","").strip()
TWILIO_WA_FROM = os.environ.get("TWILIO_WHATSAPP_FROM","whatsapp:+14155238886").strip()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
SENDGRID_KEY = os.environ.get("SENDGRID_API_KEY","").strip()
FROM_EMAIL   = os.environ.get("FROM_EMAIL","alerts@glitztracker.com").strip()


def send_sms(to_number: str, message: str) -> bool:
    """Send SMS via Twilio. to_number must be E.164 e.g. +19725551234"""
    if not (TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM):
        log.warning("Twilio not configured — skipping SMS.")
        return False
    if not to_number:
        return False
    try:
        from twilio.rest import Client
        msg = Client(TWILIO_SID, TWILIO_TOKEN).messages.create(
            body=message[:1600], from_=TWILIO_FROM, to=to_number)
        log.info("SMS sent to %s (sid: %s)", to_number, msg.sid)
        return True
    except Exception as e:
        log.error("SMS failed to %s: %s", to_number, e)
        return False


def send_whatsapp(to_number: str, message: str) -> bool:
    """Send WhatsApp via Twilio. Sandbox: TWILIO_WHATSAPP_FROM=whatsapp:+14155238886"""
    if not (TWILIO_SID and TWILIO_TOKEN):
        log.warning("Twilio not configured — skipping WhatsApp.")
        return False
    if not to_number:
        return False
    try:
        from twilio.rest import Client
        msg = Client(TWILIO_SID, TWILIO_TOKEN).messages.create(
            body=message[:1600],
            from_=TWILIO_WA_FROM,
            to=f"whatsapp:{to_number}")
        log.info("WhatsApp sent to %s (sid: %s)", to_number, msg.sid)
        return True
    except Exception as e:
        log.error("WhatsApp failed to %s: %s", to_number, e)
        return False


def send_telegram(chat_id: str, message: str) -> bool:
    if not (TELEGRAM_TOKEN and chat_id):
        return False
    try:
        import requests
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": message}, timeout=30)
        ok = r.status_code == 200
        if not ok:
            log.error("Telegram failed: %s", r.text[:200])
        return ok
    except Exception as e:
        log.error("Telegram failed: %s", e)
        return False


def send_email(to_email: str, subject: str, body: str) -> bool:
    if not (SENDGRID_KEY and to_email):
        log.info("EMAIL (no SendGrid) → %s: %s", to_email, subject)
        return True
    try:
        import requests
        r = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {SENDGRID_KEY}",
                     "Content-Type": "application/json"},
            json={"personalizations":[{"to":[{"email":to_email}]}],
                  "from":{"email":FROM_EMAIL,"name":"GlitzTracker"},
                  "subject":subject,
                  "content":[{"type":"text/plain","value":body}]},
            timeout=30)
        ok = r.status_code in (200, 202)
        if not ok:
            log.error("SendGrid failed: %s", r.text[:200])
        return ok
    except Exception as e:
        log.error("Email failed: %s", e)
        return False


def notify_user(user, message: str, subject: str = "GlitzTracker Alert") -> bool:
    """Send to all enabled channels. Returns True if at least one succeeded."""
    sent = False

    if user.notify_telegram and user.telegram_chat_id:
        sent = send_telegram(user.telegram_chat_id, message) or sent

    if user.notify_sms and user.phone_number and user.phone_verified:
        sent = send_sms(user.phone_number, _trim(message)) or sent

    if getattr(user, 'notify_whatsapp', False) and user.phone_number and user.phone_verified:
        sent = send_whatsapp(user.phone_number, _trim(message)) or sent

    if user.notify_email:
        sent = send_email(user.effective_email, subject, message) or sent

    if not user.any_notify_enabled:
        log.warning("User %d has no channels enabled.", user.id)

    return sent


def send_verification_sms(to_number: str, code: str) -> bool:
    body = f"GlitzTracker verification code: {code}\nExpires in 10 minutes."
    return send_sms(to_number, body)


def _trim(message: str, limit: int = 480) -> str:
    return message if len(message) <= limit else message[:limit-3] + "..."
