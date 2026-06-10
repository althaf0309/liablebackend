from django.utils import timezone

from .models import (
    AssistAutomationAction,
    AssistAutomationLog,
    AssistReminder,
    AssistReminderStatus,
    Notification,
    NotificationAudience,
)


ACTIVE_ASSIST_STATUSES = [AssistReminderStatus.SCHEDULED, AssistReminderStatus.SENT]


def create_assist_log(reminder, action, message, actor=None, metadata=None):
    return AssistAutomationLog.objects.create(
        reminder=reminder,
        action=action,
        actor=actor,
        message=message,
        metadata=metadata or {},
    )


def create_assist_reminder(
    user,
    title,
    student_message,
    due_at,
    reminder_type,
    priority="MEDIUM",
    application=None,
    tenancy=None,
    care_ticket=None,
    support_request=None,
    created_by=None,
    assigned_to=None,
    internal_notes="",
    metadata=None,
):
    reminder = AssistReminder.objects.create(
        user=user,
        application=application,
        tenancy=tenancy,
        care_ticket=care_ticket,
        support_request=support_request,
        created_by=created_by,
        assigned_to=assigned_to,
        reminder_type=reminder_type,
        priority=priority,
        title=title,
        student_message=student_message,
        due_at=due_at,
        internal_notes=internal_notes,
        metadata=metadata or {},
    )
    create_assist_log(reminder, AssistAutomationAction.CREATED, "Assist reminder created.", actor=created_by)
    return reminder


def send_assist_reminder(reminder, actor=None):
    if reminder.status not in ACTIVE_ASSIST_STATUSES:
        return reminder
    Notification.objects.create(
        user=reminder.user,
        application=reminder.application,
        audience=NotificationAudience.STUDENT,
        title="Quantum Assist reminder",
        message=reminder.student_message,
    )
    reminder.status = AssistReminderStatus.SENT
    reminder.sent_at = reminder.sent_at or timezone.now()
    reminder.save(update_fields=["status", "sent_at", "updated_at"])
    create_assist_log(
        reminder,
        AssistAutomationAction.NOTIFICATION_SENT,
        "Reminder notification sent.",
        actor=actor,
        metadata={"due_at": reminder.due_at.isoformat()},
    )
    return reminder


def process_due_assist_reminders(now=None, actor=None):
    now = now or timezone.now()
    due_reminders = AssistReminder.objects.filter(
        status=AssistReminderStatus.SCHEDULED,
        due_at__lte=now,
    ).select_related("user", "application")
    processed = []
    for reminder in due_reminders:
        create_assist_log(
            reminder,
            AssistAutomationAction.DUE_PROCESSED,
            "Due reminder processed by Quantum Assist.",
            actor=actor,
        )
        processed.append(send_assist_reminder(reminder, actor=actor))
    return processed


def update_assist_reminder_status(reminder, status, actor=None, internal_notes=""):
    reminder.status = status
    if internal_notes:
        reminder.internal_notes = internal_notes
    if status == AssistReminderStatus.COMPLETED and not reminder.completed_at:
        reminder.completed_at = timezone.now()
        action = AssistAutomationAction.COMPLETED
        message = "Assist reminder completed."
    elif status == AssistReminderStatus.DISMISSED:
        action = AssistAutomationAction.DISMISSED
        message = "Assist reminder dismissed."
    elif status == AssistReminderStatus.CANCELLED:
        action = AssistAutomationAction.CANCELLED
        message = "Assist reminder cancelled."
    else:
        action = AssistAutomationAction.DUE_PROCESSED
        message = f"Assist reminder moved to {status}."
    reminder.save()
    create_assist_log(reminder, action, message, actor=actor)
    return reminder
