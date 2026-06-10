from django.utils import timezone

from .models import (
    CareTicket,
    CareTicketEvent,
    CareTicketEventType,
    CareTicketStatus,
    Notification,
    NotificationAudience,
    TenancyHealthEvent,
    THSEventType,
)
from .tenancy_intelligence import refresh_tenancy_health_score


CARE_NEXT_ACTIONS = {
    CareTicketStatus.OPEN: "LGS operations will review this care request.",
    CareTicketStatus.TRIAGED: "Care request reviewed and ready for assignment.",
    CareTicketStatus.ASSIGNED: "Care request assigned for follow-up.",
    CareTicketStatus.WAITING_LANDLORD: "Waiting for landlord or property-side update.",
    CareTicketStatus.WAITING_TENANT: "Waiting for tenant update.",
    CareTicketStatus.RESOLVED: "Care request resolved.",
    CareTicketStatus.CLOSED: "Care request closed.",
}


def safe_care_message(ticket):
    if ticket.student_safe_summary:
        return ticket.student_safe_summary
    return CARE_NEXT_ACTIONS.get(ticket.status, "Care request updated.")


def event_type_for_status(status, previous_status=""):
    if not previous_status:
        return CareTicketEventType.CREATED
    if status == CareTicketStatus.ASSIGNED:
        return CareTicketEventType.ASSIGNED
    if status == CareTicketStatus.WAITING_LANDLORD:
        return CareTicketEventType.LANDLORD_UPDATED
    if status == CareTicketStatus.WAITING_TENANT:
        return CareTicketEventType.TENANT_UPDATED
    if status == CareTicketStatus.RESOLVED:
        return CareTicketEventType.RESOLVED
    if status == CareTicketStatus.CLOSED:
        return CareTicketEventType.CLOSED
    return CareTicketEventType.STATUS_CHANGED


def create_care_event(ticket, actor=None, previous_status="", metadata=None):
    event = CareTicketEvent.objects.create(
        ticket=ticket,
        event_type=event_type_for_status(ticket.status, previous_status),
        from_status=previous_status or "",
        to_status=ticket.status,
        actor=actor,
        student_message=safe_care_message(ticket),
        landlord_message=f"Care request status: {ticket.get_status_display()}" if ticket.landlord_visible else "",
        admin_message=f"{ticket.title} moved from {previous_status or 'NEW'} to {ticket.status}.",
        metadata=metadata or {},
    )
    Notification.objects.create(
        user=ticket.user,
        application=ticket.application,
        audience=NotificationAudience.STUDENT,
        title="Quantum Care update",
        message=event.student_message,
    )
    landlord = getattr(ticket.property, "assigned_landlord", None)
    if landlord and ticket.landlord_visible:
        Notification.objects.create(
            user=landlord,
            application=ticket.application,
            audience=NotificationAudience.LANDLORD,
            title="Care request update",
            message=event.landlord_message or "A care request has been updated.",
        )
    sync_care_ticket_to_ths(ticket)
    return event


def update_care_ticket_status(ticket, status, actor=None, student_safe_summary="", internal_notes="", assigned_to=None):
    previous_status = ticket.status
    ticket.status = status
    if student_safe_summary:
        ticket.student_safe_summary = student_safe_summary
    if internal_notes:
        ticket.internal_notes = internal_notes
    if assigned_to is not None:
        ticket.assigned_to = assigned_to
    if status == CareTicketStatus.RESOLVED and not ticket.resolved_at:
        ticket.resolved_at = timezone.now()
    if status == CareTicketStatus.CLOSED and not ticket.closed_at:
        ticket.closed_at = timezone.now()
    ticket.save()
    if previous_status != status:
        create_care_event(
            ticket,
            actor=actor,
            previous_status=previous_status,
            metadata={"assigned_to": str(ticket.assigned_to_id) if ticket.assigned_to_id else None},
        )
    return ticket


def sync_care_ticket_to_ths(ticket):
    if not ticket.tenancy_id:
        return None
    if ticket.status in [CareTicketStatus.RESOLVED, CareTicketStatus.CLOSED]:
        event_type = THSEventType.CARE_TICKET_RESOLVED
        weight = 4
        note = f"Care request resolved: {ticket.title}"
    else:
        event_type = THSEventType.CARE_TICKET_OPENED
        weight = -6 if ticket.priority in ["HIGH", "URGENT"] else -3
        note = f"Care request open: {ticket.title}"
    TenancyHealthEvent.objects.update_or_create(
        tenancy=ticket.tenancy,
        source_type="CareTicket",
        source_id=str(ticket.id),
        event_type=event_type,
        defaults={
            "weight": weight,
            "note": note,
            "occurred_at": timezone.now(),
        },
    )
    return refresh_tenancy_health_score(ticket.tenancy)
