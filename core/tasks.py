import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_otp_email(self, to_email: str, name: str, otp: str):
    try:
        from accounts.email_utils import _send_otp_sync
        _send_otp_sync(to_email, name, otp)
    except Exception as exc:
        logger.exception("send_otp_email failed for %s", to_email)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_account_approved_email(self, to_email: str, name: str, login_email: str, temp_password: str):
    try:
        from accounts.email_utils import _send_account_approved_sync
        _send_account_approved_sync(to_email, name, login_email, temp_password)
    except Exception as exc:
        logger.exception("send_account_approved_email failed for %s", to_email)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_application_stage_email(self, to_email: str, name: str, stage_label: str, message: str, application_code: str):
    try:
        from accounts.email_utils import _send_application_stage_sync
        _send_application_stage_sync(to_email, name, stage_label, message, application_code)
    except Exception as exc:
        logger.exception("send_application_stage_email failed for %s", to_email)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_contact_admin_email(self, **data):
    try:
        from accounts.email_utils import _send_contact_admin_sync
        _send_contact_admin_sync(**data)
    except Exception as exc:
        logger.exception("send_contact_admin_email failed")
        raise self.retry(exc=exc)


@shared_task
def run_assist_reminders():
    """Celery Beat task — replaces the management command cron."""
    from core.assist import process_due_reminders
    result = process_due_reminders()
    logger.info("Assist reminders processed: %s", result)
    return result


@shared_task
def run_expire_booking_holds():
    """Expire BookingHold records past their expiry date."""
    from django.utils import timezone
    try:
        from core.models import BookingHold, BookingHoldStatus
        expired = BookingHold.objects.filter(
            status=BookingHoldStatus.APPROVED,
            expires_at__lt=timezone.now(),
        )
        count = expired.update(status=BookingHoldStatus.EXPIRED)
        logger.info("Expired %d BookingHold records", count)
        return count
    except Exception:
        logger.exception("run_expire_booking_holds failed")
        return 0


@shared_task
def run_purge_expired_documents():
    """Purge document files whose retained_until has passed."""
    from django.utils import timezone
    from core.models import StudentDocument

    qs = StudentDocument.objects.filter(
        retained_until__lt=timezone.now(),
        purged_at__isnull=True,
    )
    purged = 0
    for doc in qs.iterator():
        try:
            if doc.file and doc.file.name:
                doc.file.delete(save=False)
            doc.purged_at = timezone.now()
            doc.save(update_fields=["purged_at"])
            purged += 1
        except Exception:
            logger.exception("Failed to purge document %s", doc.id)

    logger.info("Purged %d documents via Celery task", purged)
    return purged
