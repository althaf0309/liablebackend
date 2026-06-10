from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def email_send_otp(to_email: str, name: str, otp: str):
    brand = getattr(settings, "MAIL_BRAND_NAME", "Liable")
    subject = f"{brand} Password Reset OTP"
    text = (
        f"Hi {name},\n\n"
        f"Your OTP for password reset is: {otp}\n\n"
        f"This OTP expires in 10 minutes.\n\n"
        f"If you didn’t request this, ignore this email.\n\n"
        f"Thanks,\n{brand} Team"
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.EMAIL_HOST_USER,   # ✅ force Gmail sender
        to=[to_email],
    )
    msg.send(fail_silently=False)


def email_account_approved(to_email: str, name: str, login_email: str, temp_password: str):
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
        from_email=settings.EMAIL_HOST_USER,   # ✅ force Gmail sender
        to=[to_email],
    )
    msg.send(fail_silently=False)


def email_application_stage_update(to_email: str, name: str, stage_label: str, message: str, application_code: str):
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


def email_contact_message_admin(**data):
    subject = f"New Contact: {data.get('subject') or 'No subject'}"

    body = f"""
New Contact Message

Name: {data.get('name')}
Email: {data.get('email')}
Phone: {data.get('phone') or '-'}

Message:
{data.get('message')}
""".strip()

    admin_emails = getattr(settings, "CONTACT_ADMIN_EMAILS", [])
    if isinstance(admin_emails, str):
        admin_emails = [admin_emails]

    msg = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=settings.EMAIL_HOST_USER,   # ✅ force Gmail sender
        to=admin_emails,
        reply_to=[data.get("email")] if data.get("email") else None,
    )
    msg.send(fail_silently=False)