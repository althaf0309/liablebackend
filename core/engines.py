from django.utils import timezone
import uuid

from .models import (
    ISRAscore,
    IntentForm,
    PropMatchResult,
    PropMatchScoreHistory,
    Property,
    PropertyStatus,
    RiskBand,
    Tenancy,
    TenancyStatus,
)
from .tenancy_intelligence import refresh_tenancy_health_score

MATCH_POLICY_VERSION = "QM-Y1-2"


def clamp_score(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 0
    return max(0, min(100, value))


def risk_band_for(total_score):
    if total_score >= 80:
        return RiskBand.LOW
    if total_score >= 60:
        return RiskBand.MEDIUM
    return RiskBand.HIGH


def calculate_isra_for_user(user, override=None):
    intent = getattr(user, "intent_form", None)
    override = override or {}

    if intent:
        stability = 55
        if intent.visa_expiry and intent.visa_expiry > timezone.now().date() + timezone.timedelta(days=180):
            stability += 25
        if intent.university:
            stability += 10
        if intent.move_in_date:
            stability += 5

        financial = 45
        if intent.proof_of_funds_verified:
            financial += 30
        if intent.budget_max >= 900:
            financial += 15
        elif intent.budget_max >= 650:
            financial += 8

        behavioural = 70
        if intent.lifestyle_preferences:
            behavioural += 8
        if intent.preferred_locality:
            behavioural += 6
    else:
        stability = 60
        financial = 60
        behavioural = 60

    ths_scores = []
    for tenancy in Tenancy.objects.filter(user=user).select_related("property"):
        health = getattr(tenancy, "health_score", None) or refresh_tenancy_health_score(tenancy)
        ths_scores.append(health.score)
    if ths_scores:
        avg_ths = round(sum(ths_scores) / len(ths_scores))
        if avg_ths >= 85:
            behavioural += 10
        elif avg_ths >= 75:
            behavioural += 5
        elif avg_ths < 55:
            behavioural -= 10

    stability = clamp_score(override.get("stability_score", stability))
    financial = clamp_score(override.get("financial_score", financial))
    behavioural = clamp_score(override.get("behavioural_score", behavioural))
    total = round((stability + financial + behavioural) / 3)

    recommended_max_rent = 0
    if intent:
        recommended_max_rent = int(min(intent.budget_max or 0, max(0, financial * 15)))

    score, _ = ISRAscore.objects.update_or_create(
        user=user,
        defaults={
            "stability_score": stability,
            "financial_score": financial,
            "behavioural_score": behavioural,
            "total_score": total,
            "risk_band": risk_band_for(total),
            "recommended_max_rent": recommended_max_rent,
            "notes": override.get("notes", ""),
            "flags": override.get("flags", []),
            "override_applied": bool(override),
            "override_reason": override.get("override_reason", ""),
            "calculated_at": timezone.now(),
        },
    )
    return score


def run_propmatch_for_user(user, limit=3):
    intent = getattr(user, "intent_form", None)
    if not intent:
        return []

    score = getattr(user, "isra_score", None) or calculate_isra_for_user(user)
    qs = Property.objects.filter(status=PropertyStatus.APPROVED).prefetch_related("images")

    generated = []
    run_id = uuid.uuid4()
    for prop in qs:
        active_occupancy = Tenancy.objects.filter(property=prop, status=TenancyStatus.ACTIVE).exists()
        budget_pass = intent.budget_max >= int(prop.rent_monthly)
        isra_pass = score.total_score >= prop.isra_threshold
        occupancy_pass = not active_occupancy and prop.status != PropertyStatus.RENTED
        availability_pass = True
        if prop.available_from and intent.move_in_date:
            latest_allowed = intent.move_in_date + timezone.timedelta(days=30)
            availability_pass = prop.available_from <= latest_allowed

        locality_match = bool(
            intent.preferred_locality
            and (
                intent.preferred_locality.lower() in prop.locality.lower()
                or intent.preferred_locality.lower() in prop.city.lower()
            )
        )
        city_match = intent.city.lower() in prop.city.lower()
        room_preference_match = (
            intent.room_type
            and (
                intent.room_type.lower() in prop.room_type.lower()
                or intent.room_type.lower() in prop.property_type.lower()
            )
        )
        university_distance_signal = 15 if locality_match else 10 if city_match else 2
        rent_gap = max(0, intent.budget_max - int(prop.rent_monthly))
        score_breakdown = {
            "isra": round(score.total_score * 0.45),
            "location": university_distance_signal + (12 if locality_match else 0),
            "room_preference": 8 if room_preference_match else 0,
            "budget_headroom": round(min(18, rent_gap / 25)),
            "availability": 10 if availability_pass else 0,
        }
        confidence = min(
            99,
            round(sum(score_breakdown.values())),
        )
        eligible = budget_pass and isra_pass and availability_pass and occupancy_pass
        hard_fail_reasons = []
        if not budget_pass:
            hard_fail_reasons.append("BUDGET_ABOVE_STUDENT_RANGE")
        if not isra_pass:
            hard_fail_reasons.append("ISRA_BELOW_PROPERTY_THRESHOLD")
        if not availability_pass:
            hard_fail_reasons.append("OUTSIDE_MOVE_IN_WINDOW")
        if not occupancy_pass:
            hard_fail_reasons.append("PROPERTY_CURRENTLY_OCCUPIED")
        student_rationale = [
            "Within stated budget" if budget_pass else "Rent is above your stated budget",
            "Meets property readiness threshold" if isra_pass else "More verification may be needed before this property",
            "Available near your move-in window" if availability_pass else "Availability may not fit your move-in date",
            "Location preference signal found" if city_match or locality_match else "Location is less aligned with your preferences",
        ]
        generated.append(
            {
                "property": prop,
                "budget_pass": budget_pass,
                "isra_pass": isra_pass,
                "availability_pass": availability_pass,
                "occupancy_pass": occupancy_pass,
                "eligible": eligible,
                "confidence_score": confidence,
                "rule_version": MATCH_POLICY_VERSION,
                "score_breakdown": score_breakdown,
                "hard_fail_reasons": hard_fail_reasons,
                "student_rationale": student_rationale,
                "rationale": {
                    "budget": f"Budget GBP {intent.budget_max} vs rent GBP {prop.rent_monthly}",
                    "isra": f"ISRA {score.total_score} vs threshold {prop.isra_threshold}",
                    "availability": "Available within move-in window" if availability_pass else "Outside move-in window",
                    "occupancy": "No active tenancy" if occupancy_pass else "Currently occupied",
                    "location": "University/locality proximity signal" if city_match or locality_match else "No location boost",
                    "preference": "Room preference match" if room_preference_match else "Preference not exact",
                },
            }
        )

    ranked = sorted(
        [item for item in generated if item["eligible"]],
        key=lambda item: item["confidence_score"],
        reverse=True,
    )[:limit]
    ranked_by_property_id = {item["property"].id: index for index, item in enumerate(ranked, start=1)}

    history_rows = []
    for item in generated:
        prop = item["property"]
        history_rows.append(
            PropMatchScoreHistory(
                run_id=run_id,
                user=user,
                property=prop,
                rule_version=item["rule_version"],
                rank=ranked_by_property_id.get(prop.id),
                confidence_score=item["confidence_score"],
                eligible=item["eligible"],
                budget_pass=item["budget_pass"],
                availability_pass=item["availability_pass"],
                isra_pass=item["isra_pass"],
                occupancy_pass=item["occupancy_pass"],
                score_breakdown=item["score_breakdown"],
                hard_fail_reasons=item["hard_fail_reasons"],
                admin_rationale=item["rationale"],
                student_rationale=item["student_rationale"],
            )
        )
    PropMatchScoreHistory.objects.bulk_create(history_rows)

    PropMatchResult.objects.filter(user=user).delete()
    results = []
    for index, item in enumerate(ranked, start=1):
        results.append(
            PropMatchResult.objects.create(
                user=user,
                property=item["property"],
                rank=index,
                confidence_score=item["confidence_score"],
                budget_pass=item["budget_pass"],
                availability_pass=item["availability_pass"],
                isra_pass=item["isra_pass"],
                eligible=item["eligible"],
                rationale=item["rationale"],
                rule_version=item["rule_version"],
                score_breakdown=item["score_breakdown"],
                hard_fail_reasons=item["hard_fail_reasons"],
                student_rationale=item["student_rationale"],
            )
        )
    return results
