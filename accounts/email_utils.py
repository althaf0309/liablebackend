"""
Email sending helpers.

Public API (`email_*` functions) — dispatch via Celery when broker is reachable,
fall back to synchronous send in dev / when Celery is not configured.

Internal `_*_sync` functions are called directly by Celery tasks.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def _celery_available() -> bool:
    """Return True only if a real Celery broker URL is configured."""
    broker = getattr(settings, "CELERY_BROKER_URL", "")
    return bool(broker and not broker.startswith("memory://"))


# ── Internal sync senders (called by Celery tasks) ──────────────────────────

def _send_otp_sync(to_email: str, name: str, otp: str):
    brand = getattr(settings, "MAIL_BRAND_NAME", "Liable")
    subject = f"{brand} Password Reset OTP"
    text = (
        f"Hi {name},\n\n"
        f"Your OTP for password reset is: {otp}\n\n"
        f"This OTP expires in 10 minutes.\n\n"
        f"If you didn't request this, ignore this email.\n\n"
        f"Thanks,\n{brand} Team"
    )
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.EMAIL_HOST_USER,
        to=[to_email],
    )
    msg.send(fail_silently=False)


def _send_account_approved_sync(to_email: str, name: str, login_email: str, temp_password: str):
    brand = getattr(settings, "MAIL_BRAND_NAME", "Liable")
    subject = f"{brand} Account Approved - Login Details"
    text = (
        f"Hi {name},\n\n"
        f"Your account has been approved.\n\n"
        f"Login Email: {login_email}\n"
        f"Temporary Password: {temp_password}\n\n"
        f"Please login and change your password.\n\n"
        f"Thanks,\n{brand} Team"
    )
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.EMAIL_HOST_USER,
        to=[to_email],
    )
    msg.send(fail_silently=False)


def _send_application_stage_sync(to_email: str, name: str, stage_label: str, message: str, application_code: str):
    brand = getattr(settings, "MAIL_BRAND_NAME", "Liable")
    frontend_url = getattr(settings, "FRONTEND_BASE_URL", "")
    subject = f"{brand} Housing Journey Update — {stage_label}"
    text = (
        f"Hi {name},\n\n"
        f"{message}\n\n"
        f"Application ref: {application_code}\n\n"
        f"Log in to your dashboard to view the latest status:\n"
        f"{frontend_url}\n\n"
        f"Thanks,\n{brand} Team"
    )
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.EMAIL_HOST_USER,
        to=[to_email],
    )
    msg.send(fail_silently=False)


def _send_contact_admin_sync(**data):
    subject = f"New Contact: {data.get('subject') or 'No subject'}"
    body = f"""New Contact Message

Name: {data.get('name')}
Email: {data.get('email')}
Phone: {data.get('phone') or '-'}

Message:
{data.get('message')}""".strip()

    admin_emails = getattr(settings, "CONTACT_ADMIN_EMAILS", [])
    if isinstance(admin_emails, str):
        admin_emails = [admin_emails]

    msg = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=settings.EMAIL_HOST_USER,
        to=admin_emails,
        reply_to=[data.get("email")] if data.get("email") else None,
    )
    msg.send(fail_silently=False)


# ── Public API (route to Celery or sync) ────────────────────────────────────

def email_send_otp(to_email: str, name: str, otp: str):
    if _celery_available():
        from core.tasks import send_otp_email
        send_otp_email.delay(to_email, name, otp)
    else:
        try:
            _send_otp_sync(to_email, name, otp)
        except Exception:
            logger.exception("email_send_otp sync failed for %s", to_email)


def email_account_approved(to_email: str, name: str, login_email: str, temp_password: str):
    if _celery_available():
        from core.tasks import send_account_approved_email
        send_account_approved_email.delay(to_email, name, login_email, temp_password)
    else:
        try:
            _send_account_approved_sync(to_email, name, login_email, temp_password)
        except Exception:
            logger.exception("email_account_approved sync failed for %s", to_email)


def email_application_stage_update(to_email: str, name: str, stage_label: str, message: str, application_code: str):
    if _celery_available():
        from core.tasks import send_application_stage_email
        send_application_stage_email.delay(to_email, name, stage_label, message, application_code)
    else:
        try:
            _send_application_stage_sync(to_email, name, stage_label, message, application_code)
        except Exception:
            logger.exception("email_application_stage_update sync failed for %s", to_email)


def email_contact_message_admin(**data):
    if _celery_available():
        from core.tasks import send_contact_admin_email
        send_contact_admin_email.delay(**data)
    else:
        try:
            _send_contact_admin_sync(**data)
        except Exception:
            logger.exception("email_contact_message_admin sync failed")
