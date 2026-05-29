from django.utils import timezone

from .models import ApplicationStage, ApplicationStatus, HousingApplication


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
    return application


def create_application_for_user(user, property_obj=None, prop_match=None, target_move_in_date=None):
    application = HousingApplication.objects.create(
        user=user,
        property=property_obj,
        prop_match=prop_match,
        stage=ApplicationStage.APPLICATION,
        status=ApplicationStatus.ACTIVE,
        next_action=STAGE_NEXT_ACTIONS[ApplicationStage.APPLICATION],
        target_move_in_date=target_move_in_date,
    )
    append_stage_history(application, user, "", ApplicationStage.APPLICATION)
    application.save(update_fields=["stage_history"])
    return application
