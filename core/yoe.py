from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from .models import (
    Complaint,
    ComplaintStatus,
    Property,
    PropertyExpense,
    RentLedger,
    Tenancy,
    TenancyStatus,
    YOEMetric,
)


def _percent(numerator, denominator):
    numerator = Decimal(numerator or 0)
    denominator = Decimal(denominator or 0)
    if denominator <= 0:
        return Decimal("0.00")
    return ((numerator / denominator) * Decimal("100")).quantize(Decimal("0.01"))


def calculate_yoe_for_property(property_obj, property_value=None):
    value = Decimal(property_value or 0)
    if value <= 0:
        monthly_rent = Decimal(property_obj.rent_monthly or 0)
        value = monthly_rent * Decimal("180")

    annual_rent = Decimal(property_obj.rent_monthly or 0) * Decimal("12")
    annual_expenses = PropertyExpense.objects.filter(property=property_obj).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    active_tenancies = Tenancy.objects.filter(property=property_obj, status=TenancyStatus.ACTIVE).count()
    occupancy_rate = Decimal("100.00") if active_tenancies else Decimal("0.00")

    ledger = RentLedger.objects.filter(tenancy__property=property_obj)
    ledger_due = ledger.aggregate(total=Sum("rent_amount"))["total"] or Decimal("0")
    ledger_paid = ledger.aggregate(total=Sum("paid_amount"))["total"] or Decimal("0")
    rent_collection_rate = _percent(ledger_paid, ledger_due)

    gross_yield = _percent(annual_rent, value)
    net_yield = _percent(annual_rent - annual_expenses, value)
    open_complaints = Complaint.objects.filter(property=property_obj).exclude(status=ComplaintStatus.RESOLVED).count()

    if open_complaints:
        recommendation = "Resolve open complaints before increasing rent."
    elif net_yield < Decimal("4.00"):
        recommendation = "Review pricing or reduce recurring expenses."
    elif occupancy_rate < Decimal("100.00"):
        recommendation = "Prioritise PropMatch visibility to improve occupancy."
    else:
        recommendation = "Yield is healthy; maintain rent and service quality."

    metric, _ = YOEMetric.objects.update_or_create(
        property=property_obj,
        defaults={
            "landlord": property_obj.assigned_landlord,
            "property_value": value,
            "annual_rent": annual_rent,
            "annual_expenses": annual_expenses,
            "occupancy_rate": occupancy_rate,
            "gross_yield": gross_yield,
            "net_yield": net_yield,
            "rent_collection_rate": rent_collection_rate,
            "active_tenancies": active_tenancies,
            "open_complaints": open_complaints,
            "recommendation": recommendation,
            "calculated_at": timezone.now(),
        },
    )
    return metric


def refresh_yoe_metrics():
    return [calculate_yoe_for_property(property_obj) for property_obj in Property.objects.all()]
