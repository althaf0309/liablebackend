from django.utils import timezone

from .models import (
    CareTicket,
    CareTicketStatus,
    Complaint,
    ComplaintStatus,
    RentLedger,
    RentLedgerStatus,
    RiskBand,
    Tenancy,
    TenancyHealthEvent,
    TenancyHealthScore,
    TenancyRecord,
    TenancyStatus,
    THSEventType,
)


def _clamp(value, low=0, high=100):
    return max(low, min(high, int(round(value))))


def _band(score):
    if score >= 80:
        return RiskBand.LOW
    if score >= 60:
        return RiskBand.MEDIUM
    return RiskBand.HIGH


def ths_indicator_for_band(band):
    if band == RiskBand.LOW:
        return "Healthy"
    if band == RiskBand.MEDIUM:
        return "Stable"
    return "Needs Attention"


def ths_support_summary(score):
    if score >= 80:
        return "Tenancy is operating smoothly. Continue normal supportive management."
    if score >= 60:
        return "Tenancy is stable. Keep routine communication and monitor normal support signals."
    return "Tenancy needs attention. Review support actions early to reduce avoidable breakdown."


def _intake_window(end_date):
    month = end_date.month
    if month in (7, 8, 9, 10):
        return "September intake window"
    if month in (12, 1, 2):
        return "January intake window"
    if month in (5, 6):
        return "Summer transition window"
    return "Rolling placement window"


def _event(tenancy, event_type, weight, note, source_type, source_id, occurred_at=None):
    if not source_id:
        source_id = f"{tenancy.id}-{event_type}"
    TenancyHealthEvent.objects.update_or_create(
        source_type=source_type,
        source_id=str(source_id),
        event_type=event_type,
        defaults={
            "tenancy": tenancy,
            "weight": weight,
            "note": note,
            "occurred_at": occurred_at or timezone.now(),
        },
    )


def sync_tenancy_health_events(tenancy):
    for row in RentLedger.objects.filter(tenancy=tenancy):
        if row.status == RentLedgerStatus.PAID:
            _event(
                tenancy,
                THSEventType.RENT_PAID_ON_TIME,
                5,
                "Rent ledger marked paid.",
                "rent_ledger",
                row.id,
                row.paid_at or timezone.make_aware(timezone.datetime.combine(row.due_date, timezone.datetime.min.time())),
            )
        elif row.status == RentLedgerStatus.OVERDUE:
            _event(
                tenancy,
                THSEventType.RENT_LATE,
                -12,
                "Rent ledger marked overdue.",
                "rent_ledger",
                row.id,
                timezone.make_aware(timezone.datetime.combine(row.due_date, timezone.datetime.min.time())),
            )

    for complaint in Complaint.objects.filter(user=tenancy.user, property=tenancy.property):
        _event(
            tenancy,
            THSEventType.COMPLAINT_RAISED,
            -8,
            f"Complaint raised: {complaint.title}",
            "complaint",
            complaint.id,
            complaint.created_at,
        )
        if complaint.status == ComplaintStatus.RESOLVED:
            _event(
                tenancy,
                THSEventType.COMPLAINT_RESOLVED,
                4,
                f"Complaint resolved: {complaint.title}",
                "complaint_resolution",
                complaint.id,
                complaint.resolved_at or complaint.updated_at,
            )

    for ticket in CareTicket.objects.filter(tenancy=tenancy):
        if ticket.status in [CareTicketStatus.RESOLVED, CareTicketStatus.CLOSED]:
            _event(
                tenancy,
                THSEventType.CARE_TICKET_RESOLVED,
                4,
                f"Care request resolved: {ticket.title}",
                "care_ticket_resolution",
                ticket.id,
                ticket.resolved_at or ticket.closed_at or ticket.updated_at,
            )
        else:
            _event(
                tenancy,
                THSEventType.CARE_TICKET_OPENED,
                -6 if ticket.priority in ["HIGH", "URGENT"] else -3,
                f"Care request open: {ticket.title}",
                "care_ticket",
                ticket.id,
                ticket.created_at,
            )


def refresh_tenancy_health_score(tenancy):
    sync_tenancy_health_events(tenancy)
    events = list(TenancyHealthEvent.objects.filter(tenancy=tenancy).order_by("occurred_at"))
    ledger_rows = list(RentLedger.objects.filter(tenancy=tenancy))
    complaints = list(Complaint.objects.filter(user=tenancy.user, property=tenancy.property))
    care_tickets = list(CareTicket.objects.filter(tenancy=tenancy))

    rent_signal = 70
    for row in ledger_rows:
        if row.status == RentLedgerStatus.PAID:
            rent_signal += 7
        elif row.status == RentLedgerStatus.OVERDUE:
            rent_signal -= 18
        else:
            rent_signal -= 3

    complaint_signal = 80
    for complaint in complaints:
        if complaint.status == ComplaintStatus.RESOLVED:
            complaint_signal -= 2
        elif complaint.status == ComplaintStatus.IN_PROGRESS:
            complaint_signal -= 8
        else:
            complaint_signal -= 12
    for ticket in care_tickets:
        if ticket.status in [CareTicketStatus.RESOLVED, CareTicketStatus.CLOSED]:
            complaint_signal -= 1
        elif ticket.status in [CareTicketStatus.WAITING_LANDLORD, CareTicketStatus.WAITING_TENANT]:
            complaint_signal -= 6
        elif ticket.priority in ["HIGH", "URGENT"]:
            complaint_signal -= 12
        else:
            complaint_signal -= 7

    communication_signal = 75
    if tenancy.extension_requested:
        communication_signal += 4
    if complaints and all(c.status == ComplaintStatus.RESOLVED for c in complaints):
        communication_signal += 5

    rent_signal = _clamp(rent_signal)
    complaint_signal = _clamp(complaint_signal)
    communication_signal = _clamp(communication_signal)
    event_adjustment = sum(event.weight for event in events[-8:])
    score = _clamp((rent_signal * 0.5) + (complaint_signal * 0.3) + (communication_signal * 0.2) + event_adjustment)

    recent = sum(event.weight for event in events[-3:])
    trend = "UP" if recent > 3 else "DOWN" if recent < -3 else "STABLE"
    summary = ths_support_summary(score)
    reason_codes = []
    if any(row.status == RentLedgerStatus.OVERDUE for row in ledger_rows):
        reason_codes.append({"code": "RENT_BEHAVIOUR_NEEDS_REVIEW", "label": "Rent behaviour needs supportive follow-up", "severity": "HIGH", "signal": "rent_behaviour"})
    if any(row.status == RentLedgerStatus.PAID for row in ledger_rows):
        reason_codes.append({"code": "RENT_CONSISTENCY", "label": "Payment consistency supports tenancy stability", "severity": "LOW", "signal": "rent_behaviour"})
    open_complaints = [c for c in complaints if c.status != ComplaintStatus.RESOLVED]
    open_care_tickets = [t for t in care_tickets if t.status not in [CareTicketStatus.RESOLVED, CareTicketStatus.CLOSED]]
    if open_complaints or open_care_tickets:
        reason_codes.append({"code": "SUPPORT_REQUEST_OPEN", "label": "Open support issue should remain visible to operations", "severity": "MEDIUM", "signal": "complaints"})
    if open_care_tickets:
        reason_codes.append({"code": "CARE_REQUEST_OPEN", "label": "Open care request should stay visible to operations", "severity": "MEDIUM", "signal": "property_care"})
    if (complaints or care_tickets) and not open_complaints and not open_care_tickets:
        reason_codes.append({"code": "SUPPORT_REQUEST_RESOLVED", "label": "Support issue resolved through the workflow", "severity": "LOW", "signal": "property_care"})
    if tenancy.extension_requested:
        reason_codes.append({"code": "OCCUPANCY_CONTINUITY_SIGNAL", "label": "Extension request supports occupancy continuity planning", "severity": "LOW", "signal": "occupancy_continuity"})
    if communication_signal >= 75:
        reason_codes.append({"code": "COMMUNICATION_STABLE", "label": "Communication signal is stable", "severity": "LOW", "signal": "communication"})
    if tenancy.status == TenancyStatus.ACTIVE:
        reason_codes.append({"code": "TENANCY_ACTIVE", "label": "Active tenancy is included in live monitoring", "severity": "LOW", "signal": "tenancy_stability"})
    if not reason_codes:
        reason_codes.append({"code": "NO_SUPPORT_ALERTS", "label": "No support alerts currently recorded", "severity": "LOW", "signal": "tenancy_stability"})

    health, _ = TenancyHealthScore.objects.update_or_create(
        tenancy=tenancy,
        defaults={
            "score": score,
            "band": _band(score),
            "rent_signal": rent_signal,
            "complaint_signal": complaint_signal,
            "communication_signal": communication_signal,
            "trend": trend,
            "summary": summary,
            "reason_codes": reason_codes[:5],
            "policy_version": "THS-Y1-3",
            "calculated_at": timezone.now(),
        },
    )
    maybe_create_portable_record(tenancy, health)
    return health


def refresh_all_tenancy_health_scores():
    return [refresh_tenancy_health_score(tenancy) for tenancy in Tenancy.objects.select_related("user", "property")]


def maybe_create_portable_record(tenancy, health=None):
    if tenancy.status != TenancyStatus.ENDED:
        return None
    unresolved = Complaint.objects.filter(user=tenancy.user, property=tenancy.property).exclude(status=ComplaintStatus.RESOLVED).exists()
    unresolved_care = CareTicket.objects.filter(tenancy=tenancy).exclude(status__in=[CareTicketStatus.RESOLVED, CareTicketStatus.CLOSED]).exists()
    overdue = RentLedger.objects.filter(tenancy=tenancy, status=RentLedgerStatus.OVERDUE).exists()
    if unresolved or unresolved_care or overdue:
        return None
    health = health or getattr(tenancy, "health_score", None) or refresh_tenancy_health_score(tenancy)
    code = f"LGS-{str(tenancy.id).split('-')[0].upper()}"
    record, _ = TenancyRecord.objects.update_or_create(
        tenancy=tenancy,
        defaults={
            "user": tenancy.user,
            "property": tenancy.property,
            "badge_label": "Verified Tenancy Completion",
            "outcome": "Successful occupancy completed",
            "ths_score_snapshot": health.score,
            "certificate_code": code,
            "issued_at": timezone.now(),
        },
    )
    return record


def void_risk_rows(days=60):
    today = timezone.now().date()
    limit = today + timezone.timedelta(days=days)
    rows = []
    for tenancy in Tenancy.objects.filter(status=TenancyStatus.ACTIVE, end_date__lte=limit).select_related("property", "user"):
        days_remaining = (tenancy.end_date - today).days
        rows.append(
            {
                "tenancy_id": str(tenancy.id),
                "property": str(tenancy.property_id),
                "property_title": tenancy.property.title,
                "tenant_email": tenancy.user.email,
                "end_date": tenancy.end_date.isoformat(),
                "days_remaining": days_remaining,
                "risk_label": "Void Risk - Approaching",
                "intake_window": _intake_window(tenancy.end_date),
                "risk_level": "HIGH" if days_remaining <= 30 else "MEDIUM",
                "recommended_action": "Prepare controlled reallocation workflow and refresh PropMatch demand pool.",
            }
        )
    return rows
