import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from .models import (
    CareTicket,
    HousingApplication,
    Property,
    StudentDocument,
    SupportRequest,
    Tenancy,
    TenancyHealthScore,
)


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "how", "i", "in", "is", "it", "of", "on", "or", "our", "the", "this", "to",
    "we", "what", "when", "where", "with", "you", "your",
}

SUPPORT_GUIDANCE = [
    {
        "title": "NHS Guidance",
        "body": "For NHS support, collect the student's postcode, GP registration status, urgency, and whether they need general guidance or immediate medical help. Emergency medical issues must be directed to emergency services.",
        "type": "knowledge",
    },
    {
        "title": "Banking Guidance",
        "body": "For banking support, confirm the student's ID, proof of address, university enrolment evidence, and whether they need account-opening guidance or issue follow-up.",
        "type": "knowledge",
    },
    {
        "title": "ATS/CV Support",
        "body": "For ATS CV support, collect the target role, current CV status, skills, education details, work eligibility notes, and whether the request needs review or document preparation.",
        "type": "knowledge",
    },
    {
        "title": "Airport Pickup",
        "body": "For airport pickup, confirm arrival airport, terminal, flight number, arrival date and time, passenger count, luggage count, destination address, and contact number.",
        "type": "knowledge",
    },
    {
        "title": "Settlement Support",
        "body": "Settlement support covers move-in orientation, local transport, SIM setup, bank guidance, community introduction, NHS/GP guidance, and escalation to LGS staff when risk is high.",
        "type": "knowledge",
    },
    {
        "title": "Quantum Support Safety",
        "body": "Support replies should be helpful and staff-reviewed. Do not expose raw complaints, private documents, immigration details, or internal notes to landlords or partners.",
        "type": "policy",
    },
]


@dataclass
class RagSource:
    source_type: str
    title: str
    summary: str
    score: int
    object_id: str = ""
    url: str = ""

    def as_dict(self):
        return {
            "source_type": self.source_type,
            "title": self.title,
            "summary": self.summary,
            "score": self.score,
            "object_id": self.object_id,
            "url": self.url,
        }


def _tokens(text):
    return [token for token in re.findall(r"[a-z0-9]+", str(text).lower()) if token not in STOP_WORDS and len(token) > 1]


def _score(query_tokens, *parts):
    if not query_tokens:
        return 0
    haystack = " ".join(str(part or "") for part in parts).lower()
    return sum(3 if token in haystack else 0 for token in query_tokens) + sum(haystack.count(token) for token in query_tokens)


def _truncate(text, limit=260):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _category_hint(query_tokens):
    joined = " ".join(query_tokens)
    if any(token in joined for token in ["nhs", "gp", "doctor", "medical", "health"]):
        return "NHS_GUIDANCE"
    if any(token in joined for token in ["bank", "account", "finance"]):
        return "BANKING_GUIDANCE"
    if any(token in joined for token in ["cv", "ats", "job", "career"]):
        return "ATS_CV_SUPPORT"
    if any(token in joined for token in ["airport", "pickup", "flight", "arrival"]):
        return "AIRPORT_PICKUP"
    if any(token in joined for token in ["settle", "sim", "community", "move"]):
        return "SETTLEMENT_SUPPORT"
    return ""


def retrieve_support_context(query, support_request_id="", limit=8):
    query = str(query or "").strip()
    query_tokens = _tokens(query)
    sources = []

    for item in SUPPORT_GUIDANCE:
        score = _score(query_tokens, item["title"], item["body"])
        if score or not query_tokens:
            sources.append(RagSource(item["type"], item["title"], item["body"], score or 1))

    support_qs = SupportRequest.objects.select_related("user", "application").order_by("-updated_at")
    if support_request_id:
        support_qs = support_qs.filter(id=support_request_id)
    category = _category_hint(query_tokens)
    if category and not support_request_id:
        support_qs = support_qs.filter(Q(category=category) | Q(title__icontains=query) | Q(description__icontains=query))
    for request in support_qs[:80]:
        score = _score(
            query_tokens,
            request.title,
            request.description,
            request.category,
            request.status,
            request.student_safe_summary,
            request.user.email,
        )
        if support_request_id or score:
            sources.append(
                RagSource(
                    "support_request",
                    request.title,
                    f"{request.get_category_display()} / {request.get_status_display()} / {request.get_priority_display()}. {_truncate(request.description)}",
                    score or 6,
                    str(request.id),
                    f"/admin/support",
                )
            )

    for ticket in CareTicket.objects.select_related("user", "property").order_by("-updated_at")[:60]:
        score = _score(query_tokens, ticket.title, ticket.description, ticket.category, ticket.status, ticket.property.title if ticket.property_id else "")
        if score:
            sources.append(
                RagSource(
                    "care_ticket",
                    ticket.title,
                    f"{ticket.get_category_display()} / {ticket.get_status_display()} / {ticket.get_priority_display()}. {_truncate(ticket.description)}",
                    score,
                    str(ticket.id),
                    "/admin/care",
                )
            )

    for application in HousingApplication.objects.select_related("user", "property").order_by("-updated_at")[:60]:
        score = _score(
            query_tokens,
            application.application_code,
            application.user.email,
            application.property.title if application.property_id else "",
            application.stage,
            application.entry_status,
            application.next_action,
        )
        if score:
            sources.append(
                RagSource(
                    "application",
                    application.application_code,
                    f"{application.get_stage_display()} / {application.get_entry_status_display()}. Next action: {_truncate(application.next_action)}",
                    score,
                    str(application.id),
                    "/admin/applications",
                )
            )

    for document in StudentDocument.objects.select_related("user", "application").order_by("-uploaded_at")[:60]:
        score = _score(query_tokens, document.user.email, document.document_type, document.verification_status, document.review_notes)
        if score:
            sources.append(
                RagSource(
                    "document",
                    document.get_document_type_display(),
                    f"{document.user.email}: {document.get_verification_status_display()}. Review note: {_truncate(document.review_notes)}",
                    score,
                    str(document.id),
                    "/admin/documents",
                )
            )

    for property_obj in Property.objects.select_related("assigned_landlord").order_by("-updated_at")[:60]:
        score = _score(query_tokens, property_obj.title, property_obj.city, property_obj.locality, property_obj.property_type, property_obj.status)
        if score:
            sources.append(
                RagSource(
                    "property",
                    property_obj.title,
                    f"{property_obj.city} {property_obj.locality or ''}. {property_obj.get_status_display()}. Rent {property_obj.currency} {property_obj.rent_monthly}.",
                    score,
                    str(property_obj.id),
                    "/admin/properties",
                )
            )

    for tenancy in Tenancy.objects.select_related("user", "property").order_by("-updated_at")[:50]:
        score = _score(query_tokens, tenancy.user.email, tenancy.property.title if tenancy.property_id else "", tenancy.status)
        if score:
            health = TenancyHealthScore.objects.filter(tenancy=tenancy).first()
            health_text = f"THS {health.band} {health.score}" if health else "THS not calculated"
            sources.append(
                RagSource(
                    "tenancy",
                    tenancy.user.email,
                    f"{tenancy.property.title if tenancy.property_id else 'Property'} / {tenancy.get_status_display()} / {health_text}.",
                    score,
                    str(tenancy.id),
                    "/admin/tenancies",
                )
            )

    return sorted(sources, key=lambda row: row.score, reverse=True)[:limit]


def _fallback_answer(query, sources):
    if not sources:
        return {
            "answer": "No close support context was found. Ask for the student's request type, urgency, contact details, and any linked application before replying.",
            "draft_reply": "Thanks for contacting LGS Support. Please share a few more details so our team can guide you correctly.",
            "next_actions": [
                "Confirm the support category and urgency.",
                "Link the request to the student profile or housing application.",
                "Add a student-safe update after staff review.",
            ],
        }
    first = sources[0]
    return {
        "answer": f"Most relevant context: {first.title}. {first.summary}",
        "draft_reply": "Thanks for contacting LGS Support. We have reviewed your request and will guide you through the next step. Please keep any relevant documents or timing details ready so the team can help quickly.",
        "next_actions": [
            "Review the retrieved sources before sending any reply.",
            "Update the support request category, priority, and student-safe summary.",
            "Create a Quantum Assist reminder if follow-up is needed.",
        ],
    }


def _openai_response(query, sources):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None, "not_configured"

    model = os.getenv("OPENAI_SUPPORT_MODEL", "gpt-5-mini").strip() or "gpt-5-mini"
    context = "\n\n".join(
        f"[{idx + 1}] {source.source_type}: {source.title}\n{source.summary}"
        for idx, source in enumerate(sources[:6])
    )
    prompt = (
        "You are Quantum Support Assist for LGS. Use only the provided context. "
        "Produce JSON with keys answer, draft_reply, next_actions. "
        "Do not expose internal notes, raw private documents, immigration details, or unsupported claims.\n\n"
        f"Question: {query}\n\nContext:\n{context}"
    )
    payload = {
        "model": model,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "support_assist_response",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "answer": {"type": "string"},
                        "draft_reply": {"type": "string"},
                        "next_actions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 5,
                        },
                    },
                    "required": ["answer", "draft_reply", "next_actions"],
                },
                "strict": True,
            }
        },
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(os.getenv("OPENAI_TIMEOUT", "20"))) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None, "error"

    output_text = data.get("output_text", "")
    if not output_text:
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    output_text += content.get("text", "")
    try:
        parsed = json.loads(output_text)
    except ValueError:
        return None, "error"
    return {
        "answer": _truncate(parsed.get("answer"), 1200),
        "draft_reply": _truncate(parsed.get("draft_reply"), 1200),
        "next_actions": [str(item)[:220] for item in parsed.get("next_actions", [])[:5]],
    }, model


def build_support_intelligence(query, support_request_id=""):
    sources = retrieve_support_context(query, support_request_id=support_request_id)
    generated, model_status = _openai_response(query, sources)
    fallback = _fallback_answer(query, sources)
    response = generated or fallback
    return {
        "generated_at": timezone.now().isoformat(),
        "query": str(query or "").strip(),
        "mode": "rag",
        "retrieval": "lexical_operational_search",
        "model": model_status,
        "answer": response["answer"],
        "draft_reply": response["draft_reply"],
        "next_actions": response["next_actions"],
        "sources": [source.as_dict() for source in sources],
        "coverage": {
            "source_count": len(sources),
            "uses_openai": bool(generated),
            "privacy_note": "Private documents are not exposed; only operational metadata and staff-safe summaries are used.",
        },
    }
