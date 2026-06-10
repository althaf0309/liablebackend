from django.utils import timezone

from .models import (
    Notification,
    NotificationAudience,
    SupportRequestEvent,
    SupportRequestEventType,
    SupportRequestStatus,
)


SUPPORT_NEXT_ACTIONS = {
    SupportRequestStatus.OPEN: "LGS support will review this request.",
    SupportRequestStatus.TRIAGED: "Support request reviewed and ready for follow-up.",
    SupportRequestStatus.ASSIGNED: "Support request assigned for follow-up.",
    SupportRequestStatus.WAITING_STUDENT: "Waiting for your update.",
    SupportRequestStatus.WAITING_PARTNER: "Waiting for partner or service-side update.",
    SupportRequestStatus.RESOLVED: "Support request resolved.",
    SupportRequestStatus.CLOSED: "Support request closed.",
}


def safe_support_message(support_request):
    if support_request.student_safe_summary:
        return support_request.student_safe_summary
    return SUPPORT_NEXT_ACTIONS.get(support_request.status, "Support request updated.")


def event_type_for_support_status(status, previous_status=""):
    if not previous_status:
        return SupportRequestEventType.CREATED
    if status == SupportRequestStatus.ASSIGNED:
        return SupportRequestEventType.ASSIGNED
    if status == SupportRequestStatus.WAITING_STUDENT:
        return SupportRequestEventType.STUDENT_UPDATED
    if status == SupportRequestStatus.WAITING_PARTNER:
        return SupportRequestEventType.PARTNER_UPDATED
    if status == SupportRequestStatus.RESOLVED:
        return SupportRequestEventType.RESOLVED
    if status == SupportRequestStatus.CLOSED:
        return SupportRequestEventType.CLOSED
    return SupportRequestEventType.STATUS_CHANGED


def create_support_event(support_request, actor=None, previous_status="", metadata=None):
    event = SupportRequestEvent.objects.create(
        support_request=support_request,
        event_type=event_type_for_support_status(support_request.status, previous_status),
        from_status=previous_status or "",
        to_status=support_request.status,
        actor=actor,
        student_message=safe_support_message(support_request),
        admin_message=f"{support_request.title} moved from {previous_status or 'NEW'} to {support_request.status}.",
        metadata=metadata or {},
    )
    Notification.objects.create(
        user=support_request.user,
        application=support_request.application,
        audience=NotificationAudience.STUDENT,
        title="Quantum Support update",
        message=event.student_message,
    )
    return event


def update_support_request_status(
    support_request,
    status,
    actor=None,
    student_safe_summary="",
    internal_notes="",
    assigned_to=None,
):
    previous_status = support_request.status
    support_request.status = status
    if student_safe_summary:
        support_request.student_safe_summary = student_safe_summary
    if internal_notes:
        support_request.internal_notes = internal_notes
    if assigned_to is not None:
        support_request.assigned_to = assigned_to
    if status == SupportRequestStatus.RESOLVED and not support_request.resolved_at:
        support_request.resolved_at = timezone.now()
    if status == SupportRequestStatus.CLOSED and not support_request.closed_at:
        support_request.closed_at = timezone.now()
    support_request.save()
    if previous_status != status:
        create_support_event(
            support_request,
            actor=actor,
            previous_status=previous_status,
            metadata={"assigned_to": str(support_request.assigned_to_id) if support_request.assigned_to_id else None},
        )
    return support_request
