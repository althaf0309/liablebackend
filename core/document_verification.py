from django.utils import timezone

from .models import (
    ApplicationEntryStatus,
    ApplicationStage,
    DocumentRequirementStage,
    HousingApplication,
    StudentDocument,
    StudentDocumentType,
    VerificationState,
)


ENTRY_REQUIRED_DOCUMENTS = [
    StudentDocumentType.PASSPORT,
    StudentDocumentType.RIGHT_TO_RENT,
    StudentDocumentType.UNIVERSITY_CERTIFICATE,
    StudentDocumentType.PROOF_OF_FUNDS,
]


ENTRY_OPTIONAL_DOCUMENTS = [
    StudentDocumentType.GUARANTOR_OR_SPONSOR,
    StudentDocumentType.ADDRESS_HISTORY,
    StudentDocumentType.EMERGENCY_CONTACT,
]


DOCUMENT_SAFE_MESSAGES = {
    VerificationState.PENDING: "Document received and waiting for LGS verification.",
    VerificationState.APPROVED: "Document verified by LGS operations.",
    VerificationState.REJECTED: "Document needs review. Please upload an updated file or contact LGS support.",
    VerificationState.RESUBMISSION_REQUIRED: "Updated document required before verification can continue.",
    VerificationState.EXPIRED: "Document expired. Please upload a current version.",
}


def document_status_message(document):
    if document.student_message:
        return document.student_message
    return DOCUMENT_SAFE_MESSAGES.get(document.verification_status, DOCUMENT_SAFE_MESSAGES[VerificationState.PENDING])


def refresh_document_expiry(document, save=True):
    if (
        document.expiry_date
        and document.expiry_date < timezone.now().date()
        and document.verification_status != VerificationState.EXPIRED
    ):
        document.verification_status = VerificationState.EXPIRED
        if save:
            document.save(update_fields=["verification_status"])
    return document


def verification_summary_for_user(user, application=None):
    documents = StudentDocument.objects.filter(user=user)
    if application:
        documents = documents.filter(application__in=[application, None])
    latest_by_type = {}
    for document in documents.order_by("document_type", "-uploaded_at"):
        refresh_document_expiry(document)
        latest_by_type.setdefault(document.document_type, document)

    required_rows = []
    approved_count = 0
    blocking_count = 0
    today = timezone.now().date()
    for document_type in ENTRY_REQUIRED_DOCUMENTS:
        document = latest_by_type.get(document_type)
        status = document.verification_status if document else "MISSING"
        if document and document.expiry_date and document.expiry_date < today:
            status = VerificationState.EXPIRED
        is_approved = status == VerificationState.APPROVED
        is_blocking = status in ["MISSING", VerificationState.REJECTED, VerificationState.RESUBMISSION_REQUIRED, VerificationState.EXPIRED]
        approved_count += 1 if is_approved else 0
        blocking_count += 1 if is_blocking else 0
        required_rows.append(
            {
                "document_type": document_type,
                "label": StudentDocumentType(document_type).label,
                "required": True,
                "status": status,
                "document_id": str(document.id) if document else None,
                "expires_at": document.expiry_date.isoformat() if document and document.expiry_date else None,
                "student_message": document_status_message(document) if document else "Required document not uploaded yet.",
            }
        )

    optional_rows = []
    for document_type in ENTRY_OPTIONAL_DOCUMENTS:
        document = latest_by_type.get(document_type)
        optional_rows.append(
            {
                "document_type": document_type,
                "label": StudentDocumentType(document_type).label,
                "required": False,
                "status": document.verification_status if document else "NOT_UPLOADED",
                "document_id": str(document.id) if document else None,
                "expires_at": document.expiry_date.isoformat() if document and document.expiry_date else None,
                "student_message": document_status_message(document) if document else "Optional supporting document.",
            }
        )

    ready_for_verification = approved_count == len(ENTRY_REQUIRED_DOCUMENTS)
    return {
        "required_total": len(ENTRY_REQUIRED_DOCUMENTS),
        "required_approved": approved_count,
        "blocking_count": blocking_count,
        "ready_for_verification": ready_for_verification,
        "required": required_rows,
        "optional": optional_rows,
        "privacy_note": "Private documents are visible only to the student and LGS operations. Landlords receive readiness signals, not sensitive files.",
    }


def refresh_application_verification_state(application):
    if not application:
        return None
    summary = verification_summary_for_user(application.user, application=application)
    update_fields = []
    if summary["ready_for_verification"] and application.entry_status != ApplicationEntryStatus.READY:
        application.entry_status = ApplicationEntryStatus.READY
        application.entry_reviewed_at = timezone.now()
        update_fields.extend(["entry_status", "entry_reviewed_at", "updated_at"])
    elif (
        not summary["ready_for_verification"]
        and application.entry_status == ApplicationEntryStatus.READY
    ):
        application.entry_status = ApplicationEntryStatus.IN_REVIEW
        update_fields.extend(["entry_status", "updated_at"])
    if application.stage == ApplicationStage.APPLICATION and application.entry_status == ApplicationEntryStatus.READY:
        previous_stage = application.stage
        application.stage = ApplicationStage.VERIFICATION
        update_fields.extend(["stage", "updated_at"])
    if update_fields:
        application.save(update_fields=list(dict.fromkeys(update_fields)))
        if "stage" in update_fields:
            from .quantum_flow import create_timeline_event

            create_timeline_event(application, None, previous_stage, application.stage)
    return summary


def refresh_user_open_applications(user):
    summaries = {}
    for application in HousingApplication.objects.filter(user=user, status="ACTIVE"):
        summaries[str(application.id)] = refresh_application_verification_state(application)
    return summaries
