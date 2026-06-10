from django.db.models import Avg, Count
from django.utils import timezone

from accounts.models import User, UserRole

from .models import (
    ApplicationEntryStatus,
    ApplicationStage,
    ApplicationStatus,
    ApplicationTimelineEvent,
    AssistReminder,
    AssistReminderStatus,
    AuditLog,
    CareTicket,
    CareTicketPriority,
    CareTicketStatus,
    HousingApplication,
    Notification,
    PropMatchResult,
    PropMatchScoreHistory,
    Property,
    PropertyStatus,
    StudentDocument,
    SupportRequest,
    SupportRequestPriority,
    SupportRequestStatus,
    Tenancy,
    TenancyHealthScore,
    TenancyStatus,
    VerificationState,
    YOEMetric,
)
from .tenancy_intelligence import void_risk_rows


def _round_number(value, places=2):
    if value is None:
        return 0
    return round(float(value), places)


def _choice_counts(model, field, choices):
    rows = model.objects.values(field).annotate(count=Count("id"))
    counts = {row[field]: row["count"] for row in rows}
    return [
        {
            "key": value,
            "name": label,
            "value": counts.get(value, 0),
        }
        for value, label in choices
    ]


def _open_count(model, field, closed_statuses):
    return model.objects.exclude(**{f"{field}__in": closed_statuses}).count()


def _risk_item(title, count, severity, source, action):
    return {
        "title": title,
        "count": count,
        "severity": severity,
        "source": source,
        "action": action,
    }


def build_production_report():
    now = timezone.now()
    thirty_days_ago = now - timezone.timedelta(days=30)
    seven_days_ago = now - timezone.timedelta(days=7)
    today = timezone.localdate()

    void_rows = void_risk_rows()
    yoe_aggregate = YOEMetric.objects.aggregate(
        avg_occupancy_rate=Avg("occupancy_rate"),
        avg_net_yield=Avg("net_yield"),
        avg_collection_rate=Avg("rent_collection_rate"),
    )
    ths_aggregate = TenancyHealthScore.objects.aggregate(avg_score=Avg("score"))
    propmatch_aggregate = PropMatchResult.objects.aggregate(avg_confidence=Avg("confidence_score"))

    open_care_statuses = [CareTicketStatus.RESOLVED, CareTicketStatus.CLOSED]
    open_support_statuses = [SupportRequestStatus.RESOLVED, SupportRequestStatus.CLOSED]
    inactive_reminder_statuses = [
        AssistReminderStatus.COMPLETED,
        AssistReminderStatus.DISMISSED,
        AssistReminderStatus.CANCELLED,
    ]

    due_assist_count = AssistReminder.objects.filter(
        status=AssistReminderStatus.SCHEDULED,
        due_at__lte=now,
    ).count()
    attention_ths_count = TenancyHealthScore.objects.filter(score__lt=65).count()
    urgent_care_count = CareTicket.objects.exclude(status__in=open_care_statuses).filter(
        priority=CareTicketPriority.URGENT
    ).count()
    urgent_support_count = SupportRequest.objects.exclude(status__in=open_support_statuses).filter(
        priority=SupportRequestPriority.URGENT
    ).count()
    pending_documents_count = StudentDocument.objects.filter(
        verification_status__in=[VerificationState.PENDING, VerificationState.RESUBMISSION_REQUIRED]
    ).count()
    returned_entry_count = HousingApplication.objects.filter(entry_status=ApplicationEntryStatus.RETURNED).count()

    recent_audit = list(
        AuditLog.objects.select_related("actor")
        .order_by("-created_at")
        .values("action", "target_type", "target_id", "created_at")[:10]
    )

    risks = [
        _risk_item(
            "Tenancies needing attention",
            attention_ths_count,
            "high" if attention_ths_count else "normal",
            "Quantum THS",
            "Review tenancy health and support signals.",
        ),
        _risk_item(
            "Urgent open care tickets",
            urgent_care_count,
            "high" if urgent_care_count else "normal",
            "Quantum Care",
            "Assign owner and update resolution plan.",
        ),
        _risk_item(
            "Urgent open support requests",
            urgent_support_count,
            "high" if urgent_support_count else "normal",
            "Quantum Support",
            "Triage student support and partner dependencies.",
        ),
        _risk_item(
            "Due assist reminders",
            due_assist_count,
            "medium" if due_assist_count else "normal",
            "Quantum Assist",
            "Run due reminder processing or complete stale reminders.",
        ),
        _risk_item(
            "Document review queue",
            pending_documents_count,
            "medium" if pending_documents_count else "normal",
            "Quantum Verify",
            "Review pending and resubmission-required documents.",
        ),
        _risk_item(
            "Returned entry applications",
            returned_entry_count,
            "medium" if returned_entry_count else "normal",
            "Quantum Entry",
            "Follow up returned intake applications.",
        ),
        _risk_item(
            "Void-risk properties",
            len(void_rows),
            "medium" if void_rows else "normal",
            "Quantum Flow",
            "Review occupancy continuity windows.",
        ),
    ]

    return {
        "generated_at": now.isoformat(),
        "window": {
            "last_7_days_start": seven_days_ago.isoformat(),
            "last_30_days_start": thirty_days_ago.isoformat(),
        },
        "summary": {
            "total_students": User.objects.filter(role=UserRole.STUDENT).count(),
            "total_landlords": User.objects.filter(role=UserRole.LANDLORD).count(),
            "total_properties": Property.objects.count(),
            "approved_properties": Property.objects.filter(status=PropertyStatus.APPROVED).count(),
            "rented_properties": Property.objects.filter(status=PropertyStatus.RENTED).count(),
            "total_applications": HousingApplication.objects.count(),
            "active_applications": HousingApplication.objects.filter(status=ApplicationStatus.ACTIVE).count(),
            "active_tenancies": Tenancy.objects.filter(status=TenancyStatus.ACTIVE).count(),
            "avg_occupancy_rate": _round_number(yoe_aggregate["avg_occupancy_rate"]),
            "avg_net_yield": _round_number(yoe_aggregate["avg_net_yield"]),
            "avg_rent_collection_rate": _round_number(yoe_aggregate["avg_collection_rate"]),
            "avg_ths_score": _round_number(ths_aggregate["avg_score"], 1),
            "avg_match_confidence": _round_number(propmatch_aggregate["avg_confidence"], 1),
            "open_care_tickets": _open_count(CareTicket, "status", open_care_statuses),
            "open_support_requests": _open_count(SupportRequest, "status", open_support_statuses),
            "due_assist_reminders": due_assist_count,
        },
        "distributions": {
            "property_status": _choice_counts(Property, "status", PropertyStatus.choices),
            "application_stage": _choice_counts(HousingApplication, "stage", ApplicationStage.choices),
            "application_entry_status": _choice_counts(
                HousingApplication, "entry_status", ApplicationEntryStatus.choices
            ),
            "document_verification": _choice_counts(StudentDocument, "verification_status", VerificationState.choices),
            "care_status": _choice_counts(CareTicket, "status", CareTicketStatus.choices),
            "support_status": _choice_counts(SupportRequest, "status", SupportRequestStatus.choices),
            "assist_status": _choice_counts(AssistReminder, "status", AssistReminderStatus.choices),
        },
        "quantum_entry": {
            "submitted_last_7_days": HousingApplication.objects.filter(created_at__gte=seven_days_ago).count(),
            "review_queue": HousingApplication.objects.filter(
                entry_status__in=[ApplicationEntryStatus.SUBMITTED, ApplicationEntryStatus.IN_REVIEW]
            ).count(),
            "ready_for_verification": HousingApplication.objects.filter(
                entry_status=ApplicationEntryStatus.READY
            ).count(),
        },
        "quantum_match": {
            "current_results": PropMatchResult.objects.count(),
            "eligible_results": PropMatchResult.objects.filter(eligible=True).count(),
            "history_rows": PropMatchScoreHistory.objects.count(),
            "history_rows_last_30_days": PropMatchScoreHistory.objects.filter(generated_at__gte=thirty_days_ago).count(),
            "avg_confidence": _round_number(propmatch_aggregate["avg_confidence"], 1),
        },
        "quantum_flow": {
            "timeline_events_last_30_days": ApplicationTimelineEvent.objects.filter(
                created_at__gte=thirty_days_ago
            ).count(),
            "notifications_last_30_days": Notification.objects.filter(created_at__gte=thirty_days_ago).count(),
            "unread_notifications": Notification.objects.filter(read_at__isnull=True).count(),
        },
        "operations": {
            "care": {
                "open": _open_count(CareTicket, "status", open_care_statuses),
                "urgent_open": urgent_care_count,
                "waiting_landlord": CareTicket.objects.filter(status=CareTicketStatus.WAITING_LANDLORD).count(),
                "resolved_last_30_days": CareTicket.objects.filter(resolved_at__gte=thirty_days_ago).count(),
            },
            "support": {
                "open": _open_count(SupportRequest, "status", open_support_statuses),
                "urgent_open": urgent_support_count,
                "waiting_partner": SupportRequest.objects.filter(status=SupportRequestStatus.WAITING_PARTNER).count(),
                "resolved_last_30_days": SupportRequest.objects.filter(resolved_at__gte=thirty_days_ago).count(),
            },
            "assist": {
                "scheduled": AssistReminder.objects.filter(status=AssistReminderStatus.SCHEDULED).count(),
                "due": due_assist_count,
                "sent_last_30_days": AssistReminder.objects.filter(sent_at__gte=thirty_days_ago).count(),
                "completed_last_30_days": AssistReminder.objects.filter(completed_at__gte=thirty_days_ago).count(),
                "active": AssistReminder.objects.exclude(status__in=inactive_reminder_statuses).count(),
            },
            "documents": {
                "pending_or_resubmission": pending_documents_count,
                "approved": StudentDocument.objects.filter(verification_status=VerificationState.APPROVED).count(),
                "expired": StudentDocument.objects.filter(
                    verification_status=VerificationState.EXPIRED
                ).count()
                + StudentDocument.objects.filter(expiry_date__lt=today).exclude(expiry_date__isnull=True).count(),
            },
            "tenancy_health": {
                "average_score": _round_number(ths_aggregate["avg_score"], 1),
                "needs_attention": attention_ths_count,
                "active_tenancies": Tenancy.objects.filter(status=TenancyStatus.ACTIVE).count(),
                "ending_next_60_days": Tenancy.objects.filter(
                    status=TenancyStatus.ACTIVE,
                    end_date__gte=today,
                    end_date__lte=today + timezone.timedelta(days=60),
                ).count(),
            },
        },
        "occupancy": {
            "void_risk_count": len(void_rows),
            "void_risk_rows": void_rows[:10],
            "yoe_metric_count": YOEMetric.objects.count(),
            "avg_occupancy_rate": _round_number(yoe_aggregate["avg_occupancy_rate"]),
            "avg_net_yield": _round_number(yoe_aggregate["avg_net_yield"]),
            "avg_rent_collection_rate": _round_number(yoe_aggregate["avg_collection_rate"]),
        },
        "risks": risks,
        "recent_audit": recent_audit,
    }
