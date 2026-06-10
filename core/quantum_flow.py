import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

from .models import (
    ApplicationEntryStatus,
    ApplicationIntakeSource,
    ApplicationStage,
    ApplicationStatus,
    ApplicationTimelineEvent,
    HousingApplication,
    Notification,
    NotificationAudience,
    TimelineEventType,
)


STAGE_NEXT_ACTIONS = {
    ApplicationStage.APPLICATION: "Confirm student intent and required details.",
    ApplicationStage.VERIFICATION: "Review identity, university, visa, and funds documents.",
    ApplicationStage.MATCHING: "Generate or review controlled PropMatch recommendations.",
    ApplicationStage.MOVE_IN: "Coordinate agreement, booking hold, payment, and move-in support.",
    ApplicationStage.CARE: "Monitor support, maintenance, and tenancy care signals.",
    ApplicationStage.SUPPORT: "Resolve active support request before continuing the journey.",
    ApplicationStage.RENEWAL: "Review renewal or controlled reallocation options.",
    ApplicationStage.COMPLETED: "Issue completion record where eligibility is met.",
    ApplicationStage.CANCELLED: "Close application and preserve audit history.",
}


def flow_stage_label(stage):
    return dict(ApplicationStage.choices).get(stage, stage)


def flow_progress_index(stage):
    order = [
        ApplicationStage.APPLICATION,
        ApplicationStage.VERIFICATION,
        ApplicationStage.MATCHING,
        ApplicationStage.MOVE_IN,
        ApplicationStage.CARE,
        ApplicationStage.RENEWAL,
        ApplicationStage.COMPLETED,
    ]
    try:
        return order.index(stage) + 1
    except ValueError:
        return 0


def append_stage_history(application, actor, previous_stage, new_stage):
    history = list(application.stage_history or [])
    history.append(
        {
            "from": previous_stage,
            "to": new_stage,
            "actor_id": str(getattr(actor, "id", "")) if actor else "",
            "actor_email": getattr(actor, "email", "") if actor else "",
            "changed_at": timezone.now().isoformat(),
        }
    )
    application.stage_history = history[-20:]


def timeline_event_type_for_stage(stage, previous_stage=""):
    if not previous_stage:
        return TimelineEventType.APPLICATION_SUBMITTED
    if stage == ApplicationStage.VERIFICATION:
        return TimelineEventType.VERIFICATION_READY
    if stage == ApplicationStage.MATCHING:
        return TimelineEventType.MATCHING_STARTED
    if stage == ApplicationStage.MOVE_IN:
        return TimelineEventType.MOVE_IN_SCHEDULED
    if stage == ApplicationStage.CARE:
        return TimelineEventType.CARE_TICKET_OPENED
    if stage == ApplicationStage.SUPPORT:
        return TimelineEventType.SUPPORT_REQUEST_OPENED
    if stage == ApplicationStage.RENEWAL:
        return TimelineEventType.RENEWAL_REMINDER
    if stage == ApplicationStage.COMPLETED:
        return TimelineEventType.COMPLETED
    return TimelineEventType.STAGE_CHANGED


def create_timeline_event(application, actor, previous_stage, new_stage, notes=""):
    event_type = timeline_event_type_for_stage(new_stage, previous_stage)
    student_message = (
        f"Your housing journey moved to {flow_stage_label(new_stage)}."
        if previous_stage
        else "Your housing application has been submitted."
    )
    admin_message = (
        f"{application.application_code} moved from {flow_stage_label(previous_stage)} to {flow_stage_label(new_stage)}."
        if previous_stage
        else f"{application.application_code} submitted by {application.user.email}."
    )
    event = ApplicationTimelineEvent.objects.create(
        application=application,
        event_type=event_type,
        from_stage=previous_stage or "",
        to_stage=new_stage or "",
        actor=actor if getattr(actor, "is_authenticated", True) else None,
        student_message=notes or student_message,
        admin_message=admin_message,
        metadata={
            "application_code": application.application_code,
            "property_id": str(application.property_id) if application.property_id else None,
            "actor_id": str(getattr(actor, "id", "")) if actor else "",
        },
    )
    create_notifications_for_event(event)
    return event


EMAIL_NOTIFY_STAGES = {
    ApplicationStage.APPLICATION,
    ApplicationStage.VERIFICATION,
    ApplicationStage.MATCHING,
    ApplicationStage.MOVE_IN,
    ApplicationStage.COMPLETED,
    ApplicationStage.CANCELLED,
}


def _send_stage_email(application, event):
    if event.to_stage not in EMAIL_NOTIFY_STAGES:
        return
    try:
        from accounts.email_utils import email_application_stage_update
        user = application.user
        email_application_stage_update(
            to_email=user.email,
            name=user.full_name or user.email,
            stage_label=flow_stage_label(event.to_stage),
            message=event.student_message,
            application_code=application.application_code or str(application.id),
        )
    except Exception:
        logger.exception("Stage email failed for application %s", application.id)


def create_notifications_for_event(event):
    application = event.application
    Notification.objects.create(
        user=application.user,
        application=application,
        timeline_event=event,
        audience=NotificationAudience.STUDENT,
        title="Quantum Flow update",
        message=event.student_message,
    )
    _send_stage_email(application, event)

    landlord = getattr(application.property, "assigned_landlord", None) if application.property_id else None
    if landlord and event.to_stage in [ApplicationStage.MATCHING, ApplicationStage.MOVE_IN, ApplicationStage.CARE, ApplicationStage.RENEWAL]:
        Notification.objects.create(
            user=landlord,
            application=application,
            timeline_event=event,
            audience=NotificationAudience.LANDLORD,
            title="Property journey update",
            message=f"A matched housing journey moved to {flow_stage_label(event.to_stage)}.",
        )


def advance_application_stage(application, stage, actor=None, notes="", next_action="", previous_stage=None):
    previous_stage = previous_stage or application.stage
    application.stage = stage
    application.stage_notes = notes or application.stage_notes
    application.next_action = next_action or STAGE_NEXT_ACTIONS.get(stage, "")
    if stage == ApplicationStage.COMPLETED:
        application.status = ApplicationStatus.COMPLETED
    elif stage == ApplicationStage.CANCELLED:
        application.status = ApplicationStatus.CANCELLED
    elif application.status in [ApplicationStatus.COMPLETED, ApplicationStatus.CANCELLED]:
        application.status = ApplicationStatus.ACTIVE
    append_stage_history(application, actor, previous_stage, stage)
    application.save(update_fields=["stage", "status", "stage_notes", "next_action", "stage_history", "updated_at"])
    if previous_stage != stage:
        create_timeline_event(application, actor, previous_stage, stage, notes=notes)
    return application


def intent_snapshot_for_user(user):
    intent = getattr(user, "intent_form", None)
    if not intent:
        return {}
    return {
        "identity": intent.identity,
        "purpose": intent.purpose,
        "room_type": intent.room_type,
        "budget_min": intent.budget_min,
        "budget_max": intent.budget_max,
        "city": intent.city,
        "preferred_locality": intent.preferred_locality,
        "university": intent.university,
        "course": intent.course,
        "nationality": intent.nationality,
        "visa_type": intent.visa_type,
        "visa_expiry": intent.visa_expiry.isoformat() if intent.visa_expiry else "",
        "proof_of_funds_verified": intent.proof_of_funds_verified,
        "move_in_date": intent.move_in_date.isoformat() if intent.move_in_date else "",
        "lifestyle_preferences": intent.lifestyle_preferences,
    }


def create_application_for_user(
    user,
    property_obj=None,
    prop_match=None,
    target_move_in_date=None,
    applicant_notes="",
    intake_snapshot=None,
    intake_source=ApplicationIntakeSource.STUDENT_PORTAL,
):
    application = HousingApplication.objects.create(
        user=user,
        property=property_obj,
        prop_match=prop_match,
        entry_status=ApplicationEntryStatus.SUBMITTED,
        intake_source=intake_source,
        applicant_notes=applicant_notes,
        intake_snapshot=intake_snapshot if intake_snapshot is not None else intent_snapshot_for_user(user),
        stage=ApplicationStage.APPLICATION,
        status=ApplicationStatus.ACTIVE,
        next_action=STAGE_NEXT_ACTIONS[ApplicationStage.APPLICATION],
        target_move_in_date=target_move_in_date,
    )
    append_stage_history(application, user, "", ApplicationStage.APPLICATION)
    application.save(update_fields=["stage_history"])
    create_timeline_event(application, user, "", ApplicationStage.APPLICATION)
    return application
