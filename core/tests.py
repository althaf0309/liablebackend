import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User, UserRole

from .models import (
    AssistAutomationLog,
    AssistReminder,
    AssistReminderStatus,
    AssistReminderType,
    AuditLog,
    CareTicket,
    CareTicketAttachment,
    CareTicketPriority,
    CareTicketStatus,
    Complaint,
    ComplaintAttachment,
    ApplicationEntryStatus,
    ApplicationStage,
    ApplicationTimelineEvent,
    HousingApplication,
    IntentForm,
    ISRAscore,
    PropMatchResult,
    PropMatchScoreHistory,
    Notification,
    RentLedger,
    RentLedgerStatus,
    Property,
    PropertyStatus,
    StudentDocument,
    StudentDocumentType,
    SupportRequest,
    SupportRequestAttachment,
    SupportRequestPriority,
    SupportRequestStatus,
    Tenancy,
    TenancyHealthEvent,
    TenancyRecord,
    TenancyStatus,
    THSEventType,
    VerificationState,
    YOEMetric,
)
from .engines import run_propmatch_for_user
from .tenancy_intelligence import refresh_tenancy_health_score


class ContactSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def test_contact_create_requires_csrf(self):
        response = self.client.post(
            "/api/core/contact/public/",
            {
                "name": "Test",
                "email": "test@example.com",
                "subject": "Hello",
                "contact_type": "student",
                "message": "World",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)


class PrivateDocumentAuditTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()

        self.client = APIClient()
        self.student = User.objects.create_user(
            "student@example.com",
            "Password123!",
            role=UserRole.STUDENT,
            full_name="Test Student",
        )
        self.other_student = User.objects.create_user(
            "other@example.com",
            "Password123!",
            role=UserRole.STUDENT,
            full_name="Other Student",
        )
        self.admin = User.objects.create_user(
            "admin@example.com",
            "Password123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        self.property = Property.objects.create(
            title="London Test Studio",
            slug="london-test-studio",
            city="London",
            rent_monthly=900,
            status=PropertyStatus.APPROVED,
        )

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _authenticate(self, user):
        self.client.force_authenticate(user=user)

    def _upload_student_document(self):
        self._authenticate(self.student)
        file_obj = SimpleUploadedFile(
            "visa.pdf",
            b"%PDF-1.4 private document",
            content_type="application/pdf",
        )
        return self.client.post(
            "/api/core/me/documents/",
            {
                "document_type": StudentDocumentType.VISA,
                "file": file_obj,
            },
            format="multipart",
        )

    def _upload_complaint_attachment(self):
        complaint = Complaint.objects.create(
            user=self.student,
            property=self.property,
            title="Leak in kitchen",
            description="Water leak under sink.",
        )
        self._authenticate(self.student)
        file_obj = SimpleUploadedFile(
            "leak.jpg",
            b"fake-jpeg-bytes",
            content_type="image/jpeg",
        )
        response = self.client.post(
            f"/api/core/me/complaints/{complaint.id}/attachments/",
            {"file": file_obj},
            format="multipart",
        )
        return complaint, response

    def test_student_document_upload_and_download_are_audited(self):
        upload_response = self._upload_student_document()

        self.assertEqual(upload_response.status_code, 201)
        document = StudentDocument.objects.get(id=upload_response.data["id"])

        upload_log = AuditLog.objects.get(action="student_document.upload")
        self.assertEqual(upload_log.actor, self.student)
        self.assertEqual(upload_log.target_type, "StudentDocument")
        self.assertEqual(upload_log.target_id, str(document.id))
        self.assertEqual(upload_log.metadata["document_type"], StudentDocumentType.VISA)

        download_response = self.client.get(f"/api/core/documents/{document.id}/download/")

        self.assertEqual(download_response.status_code, 200)
        download_log = AuditLog.objects.get(action="student_document.download")
        self.assertEqual(download_log.actor, self.student)
        self.assertEqual(download_log.target_id, str(document.id))
        self.assertEqual(download_log.metadata["document_owner_id"], str(self.student.id))

    def test_other_student_cannot_download_student_document(self):
        upload_response = self._upload_student_document()
        document_id = upload_response.data["id"]

        self._authenticate(self.other_student)
        download_response = self.client.get(f"/api/core/documents/{document_id}/download/")

        self.assertEqual(download_response.status_code, 403)
        self.assertFalse(AuditLog.objects.filter(action="student_document.download").exists())

    def test_admin_can_download_student_document_and_action_is_audited(self):
        upload_response = self._upload_student_document()
        document_id = upload_response.data["id"]

        self._authenticate(self.admin)
        download_response = self.client.get(f"/api/core/documents/{document_id}/download/")

        self.assertEqual(download_response.status_code, 200)
        download_log = AuditLog.objects.get(action="student_document.download")
        self.assertEqual(download_log.actor, self.admin)
        self.assertEqual(download_log.target_id, document_id)

    def test_admin_review_sets_reviewer_and_student_view_hides_admin_notes(self):
        upload_response = self._upload_student_document()
        document_id = upload_response.data["id"]

        self._authenticate(self.admin)
        review_response = self.client.patch(
            f"/api/core/documents/{document_id}/",
            {
                "verification_status": "APPROVED",
                "admin_notes": "Internal review note for operations.",
            },
            format="json",
        )

        self.assertEqual(review_response.status_code, 200)
        document = StudentDocument.objects.get(id=document_id)
        self.assertEqual(document.reviewed_by, self.admin)
        self.assertIsNotNone(document.reviewed_at)
        self.assertEqual(review_response.data["reviewed_by_email"], self.admin.email)
        self.assertTrue(AuditLog.objects.filter(action="student_document.review").exists())

        self._authenticate(self.student)
        list_response = self.client.get("/api/core/me/documents/")

        self.assertEqual(list_response.status_code, 200)
        self.assertNotIn("admin_notes", list_response.data[0])
        self.assertNotIn("reviewed_by_email", list_response.data[0])
        self.assertEqual(list_response.data[0]["student_review_message"], "Document verified by LGS operations.")

    def test_document_pipeline_updates_application_readiness_without_exposing_private_notes(self):
        application = HousingApplication.objects.create(
            user=self.student,
            property=self.property,
            entry_status=ApplicationEntryStatus.IN_REVIEW,
        )
        required_types = [
            StudentDocumentType.PASSPORT,
            StudentDocumentType.RIGHT_TO_RENT,
            StudentDocumentType.UNIVERSITY_CERTIFICATE,
            StudentDocumentType.PROOF_OF_FUNDS,
        ]

        self._authenticate(self.student)
        for index, document_type in enumerate(required_types):
            file_obj = SimpleUploadedFile(
                f"document-{index}.pdf",
                b"%PDF-1.4 private document",
                content_type="application/pdf",
            )
            response = self.client.post(
                "/api/core/me/documents/",
                {
                    "application": str(application.id),
                    "document_type": document_type,
                    "expiry_date": (timezone.now().date() + timezone.timedelta(days=365)).isoformat(),
                    "file": file_obj,
                },
                format="multipart",
            )
            self.assertEqual(response.status_code, 201)

        self._authenticate(self.admin)
        for document in StudentDocument.objects.filter(application=application):
            response = self.client.patch(
                f"/api/core/documents/{document.id}/",
                {
                    "verification_status": VerificationState.APPROVED,
                    "admin_notes": "Internal verification evidence checked.",
                },
                format="json",
            )
            self.assertEqual(response.status_code, 200)

        application.refresh_from_db()
        self.assertEqual(application.entry_status, ApplicationEntryStatus.READY)
        self.assertEqual(application.stage, ApplicationStage.VERIFICATION)

        self._authenticate(self.student)
        application_response = self.client.get("/api/core/me/applications/")
        document_response = self.client.get("/api/core/me/documents/")

        self.assertEqual(application_response.status_code, 200)
        summary = application_response.data[0]["verification_summary"]
        self.assertTrue(summary["ready_for_verification"])
        self.assertEqual(summary["required_approved"], 4)
        self.assertIn("Private documents", summary["privacy_note"])
        self.assertNotIn("admin_notes", document_response.data[0])
        self.assertEqual(document_response.data[0]["student_review_message"], "Document verified by LGS operations.")

    def test_admin_can_request_document_resubmission_with_safe_student_message(self):
        application = HousingApplication.objects.create(user=self.student, property=self.property)
        self._authenticate(self.student)
        upload_response = self.client.post(
            "/api/core/me/documents/",
            {
                "application": str(application.id),
                "document_type": StudentDocumentType.PASSPORT,
                "file": SimpleUploadedFile("passport.pdf", b"%PDF-1.4 private document", content_type="application/pdf"),
            },
            format="multipart",
        )
        document_id = upload_response.data["id"]

        self._authenticate(self.admin)
        review_response = self.client.patch(
            f"/api/core/documents/{document_id}/",
            {
                "verification_status": VerificationState.RESUBMISSION_REQUIRED,
                "student_message": "Please upload a clearer passport scan.",
                "admin_notes": "Image blurred at passport number.",
            },
            format="json",
        )

        self.assertEqual(review_response.status_code, 200)
        document = StudentDocument.objects.get(id=document_id)
        self.assertIsNotNone(document.resubmission_requested_at)
        self.assertTrue(AuditLog.objects.filter(action="student_document.review", metadata__status=VerificationState.RESUBMISSION_REQUIRED).exists())

        self._authenticate(self.student)
        list_response = self.client.get("/api/core/me/documents/")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data[0]["student_review_message"], "Please upload a clearer passport scan.")
        self.assertNotIn("admin_notes", list_response.data[0])

    def test_complaint_attachment_upload_and_download_are_audited(self):
        complaint, upload_response = self._upload_complaint_attachment()

        self.assertEqual(upload_response.status_code, 201)
        attachment = ComplaintAttachment.objects.get(id=upload_response.data["id"])

        upload_log = AuditLog.objects.get(action="complaint_attachment.upload")
        self.assertEqual(upload_log.actor, self.student)
        self.assertEqual(upload_log.target_type, "ComplaintAttachment")
        self.assertEqual(upload_log.target_id, str(attachment.id))
        self.assertEqual(upload_log.metadata["complaint_id"], str(complaint.id))

        download_response = self.client.get(f"/api/core/complaint-attachments/{attachment.id}/download/")

        self.assertEqual(download_response.status_code, 200)
        download_log = AuditLog.objects.get(action="complaint_attachment.download")
        self.assertEqual(download_log.actor, self.student)
        self.assertEqual(download_log.target_id, str(attachment.id))
        self.assertEqual(download_log.metadata["complaint_owner_id"], str(self.student.id))

    def test_other_student_cannot_download_complaint_attachment(self):
        _, upload_response = self._upload_complaint_attachment()
        attachment_id = upload_response.data["id"]

        self._authenticate(self.other_student)
        download_response = self.client.get(f"/api/core/complaint-attachments/{attachment_id}/download/")

        self.assertEqual(download_response.status_code, 403)
        self.assertFalse(AuditLog.objects.filter(action="complaint_attachment.download").exists())


class AdminAuditLogViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            "audit-admin@example.com",
            "Password123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        self.staff = User.objects.create_user(
            "audit-staff@example.com",
            "Password123!",
            role=UserRole.STAFF,
            is_staff=True,
        )
        self.student = User.objects.create_user(
            "audit-student@example.com",
            "Password123!",
            role=UserRole.STUDENT,
        )
        AuditLog.objects.create(
            actor=self.admin,
            action="student_document.download",
            target_type="StudentDocument",
            target_id="doc-1",
            metadata={"document_type": "VISA"},
        )
        AuditLog.objects.create(
            actor=self.staff,
            action="complaint_attachment.download",
            target_type="ComplaintAttachment",
            target_id="attachment-1",
            metadata={"complaint_id": "complaint-1"},
        )

    def test_staff_can_filter_audit_logs_by_action_and_target_type(self):
        self.client.force_authenticate(user=self.staff)

        response = self.client.get(
            "/api/core/audit-logs/",
            {
                "action": "student_document",
                "target_type": "StudentDocument",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["action"], "student_document.download")
        self.assertEqual(response.data[0]["target_type"], "StudentDocument")

    def test_admin_can_filter_audit_logs_by_actor_and_target_id(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(
            "/api/core/audit-logs/",
            {
                "actor_id": str(self.staff.id),
                "target_id": "attachment-1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(str(response.data[0]["actor"]), str(self.staff.id))
        self.assertEqual(response.data[0]["target_id"], "attachment-1")

    def test_student_cannot_read_audit_logs(self):
        self.client.force_authenticate(user=self.student)

        response = self.client.get("/api/core/audit-logs/")

        self.assertEqual(response.status_code, 403)


class AdminISRAPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            "isra-admin@example.com",
            "Password123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        self.staff = User.objects.create_user(
            "isra-staff@example.com",
            "Password123!",
            role=UserRole.STAFF,
            is_staff=True,
        )
        self.student = User.objects.create_user(
            "isra-student@example.com",
            "Password123!",
            role=UserRole.STUDENT,
        )

    def _override_payload(self):
        return {
            "user": str(self.student.id),
            "stability_score": 85,
            "financial_score": 80,
            "behavioural_score": 78,
            "notes": "Reviewed against supplied documents.",
            "flags": [],
            "override_reason": "Manual verification complete.",
        }

    def test_staff_can_read_isra_scores_but_cannot_create_override(self):
        self.client.force_authenticate(user=self.staff)

        list_response = self.client.get("/api/core/isra-scores/")
        create_response = self.client.post(
            "/api/core/isra-scores/",
            self._override_payload(),
            format="json",
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(create_response.status_code, 403)
        self.assertFalse(ISRAscore.objects.filter(user=self.student).exists())

    def test_admin_can_create_isra_override(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/core/isra-scores/",
            self._override_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        score = ISRAscore.objects.get(user=self.student)
        self.assertTrue(score.override_applied)
        self.assertEqual(score.stability_score, 85)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action="isra_score.create_override",
                target_id=str(score.id),
            ).exists()
        )

    def test_student_cannot_read_isra_admin_scores(self):
        self.client.force_authenticate(user=self.student)

        response = self.client.get("/api/core/isra-scores/")

        self.assertEqual(response.status_code, 403)


class PropMatchRuleHistoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            "match-student@example.com",
            "Password123!",
            role=UserRole.STUDENT,
        )
        self.admin = User.objects.create_user(
            "match-admin@example.com",
            "Password123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        IntentForm.objects.create(
            user=self.student,
            room_type="Studio",
            budget_min=700,
            budget_max=1000,
            city="London",
            preferred_locality="Bloomsbury",
            university="UCL",
            nationality="India",
            move_in_date=timezone.now().date() + timezone.timedelta(days=30),
            proof_of_funds_verified=True,
        )
        self.match_property = Property.objects.create(
            title="Bloomsbury Studio",
            slug="bloomsbury-studio",
            city="London",
            locality="Bloomsbury",
            room_type="ENTIRE",
            property_type="STUDIO",
            rent_monthly=900,
            isra_threshold=60,
            status=PropertyStatus.APPROVED,
        )
        self.expensive_property = Property.objects.create(
            title="Expensive Studio",
            slug="expensive-studio",
            city="London",
            locality="Chelsea",
            property_type="STUDIO",
            rent_monthly=1500,
            isra_threshold=60,
            status=PropertyStatus.APPROVED,
        )

    def test_propmatch_persists_rule_history_and_student_safe_rationale(self):
        results = run_propmatch_for_user(self.student, limit=3)

        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.rule_version, "QM-Y1-2")
        self.assertIn("budget_headroom", result.score_breakdown)
        self.assertEqual(result.hard_fail_reasons, [])
        self.assertTrue(result.student_rationale)

        history = PropMatchScoreHistory.objects.filter(user=self.student)
        self.assertEqual(history.count(), 2)
        failed = history.get(property=self.expensive_property)
        self.assertFalse(failed.eligible)
        self.assertIn("BUDGET_ABOVE_STUDENT_RANGE", failed.hard_fail_reasons)

    def test_admin_can_read_propmatch_history(self):
        run_propmatch_for_user(self.student, limit=3)
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/core/propmatch/history/", {"user_id": str(self.student.id)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        self.assertIn("score_breakdown", response.data[0])
        self.assertIn("student_rationale", response.data[0])


class TenancyHealthIndicatorTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            "ths-student@example.com",
            "Password123!",
            role=UserRole.STUDENT,
        )
        self.property = Property.objects.create(
            title="THS Test Studio",
            slug="ths-test-studio",
            city="London",
            rent_monthly=900,
            status=PropertyStatus.APPROVED,
        )
        today = timezone.now().date()
        self.tenancy = Tenancy.objects.create(
            user=self.student,
            property=self.property,
            start_date=today,
            end_date=today + timezone.timedelta(days=180),
            rent_amount=900,
            status=TenancyStatus.ACTIVE,
        )

    def test_tenancy_health_uses_supportive_stable_indicator(self):
        health = refresh_tenancy_health_score(self.tenancy)

        self.assertEqual(health.band, "MEDIUM")
        self.assertIn("stable", health.summary.lower())
        self.assertIn("support", health.summary.lower())
        self.assertEqual(health.policy_version, "THS-Y1-3")
        self.assertTrue(any(reason.get("signal") == "communication" for reason in health.reason_codes))

    def test_tenancy_health_healthy_indicator_for_consistent_paid_rent(self):
        today = timezone.now().date()
        for index in range(3):
            RentLedger.objects.create(
                tenancy=self.tenancy,
                due_date=today - timezone.timedelta(days=30 * (index + 1)),
                rent_amount=900,
                paid_amount=900,
                status=RentLedgerStatus.PAID,
                paid_at=timezone.now(),
            )

        health = refresh_tenancy_health_score(self.tenancy)

        self.assertEqual(health.band, "LOW")
        self.assertIn("smoothly", health.summary.lower())
        self.assertTrue(any(reason["code"] == "RENT_CONSISTENCY" for reason in health.reason_codes))

    def test_tenancy_health_needs_attention_for_overdue_rent_and_open_complaint(self):
        RentLedger.objects.create(
            tenancy=self.tenancy,
            due_date=timezone.now().date() - timezone.timedelta(days=14),
            rent_amount=900,
            paid_amount=0,
            status=RentLedgerStatus.OVERDUE,
        )
        Complaint.objects.create(
            user=self.student,
            property=self.property,
            title="Urgent leak",
            description="Water coming through ceiling.",
        )

        health = refresh_tenancy_health_score(self.tenancy)

        self.assertEqual(health.band, "HIGH")
        self.assertIn("needs attention", health.summary.lower())
        self.assertTrue(any(reason["code"] == "RENT_BEHAVIOUR_NEEDS_REVIEW" for reason in health.reason_codes))
        self.assertTrue(any(reason["code"] == "SUPPORT_REQUEST_OPEN" for reason in health.reason_codes))


class QuantumCareTicketTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.client = APIClient()
        self.student = User.objects.create_user(
            "care-student@example.com",
            "Password123!",
            role=UserRole.STUDENT,
        )
        self.landlord = User.objects.create_user(
            "care-landlord@example.com",
            "Password123!",
            role=UserRole.LANDLORD,
        )
        self.admin = User.objects.create_user(
            "care-admin@example.com",
            "Password123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        self.property = Property.objects.create(
            title="Care Test Studio",
            slug="care-test-studio",
            city="London",
            rent_monthly=900,
            assigned_landlord=self.landlord,
            status=PropertyStatus.APPROVED,
        )
        today = timezone.now().date()
        self.tenancy = Tenancy.objects.create(
            user=self.student,
            property=self.property,
            start_date=today,
            end_date=today + timezone.timedelta(days=180),
            rent_amount=900,
            status=TenancyStatus.ACTIVE,
        )

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_student_can_create_care_ticket_and_ths_receives_signal(self):
        self.client.force_authenticate(user=self.student)

        response = self.client.post(
            "/api/core/me/care-tickets/",
            {
                "property": str(self.property.id),
                "tenancy": str(self.tenancy.id),
                "category": "MAINTENANCE",
                "priority": "HIGH",
                "title": "Heating not working",
                "description": "The heating is not working in the bedroom.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        ticket = CareTicket.objects.get(id=response.data["id"])
        self.assertEqual(ticket.status, CareTicketStatus.OPEN)
        self.assertTrue(ticket.events.filter(event_type="CREATED").exists())
        self.assertTrue(AuditLog.objects.filter(action="care_ticket.create").exists())
        self.assertTrue(TenancyHealthEvent.objects.filter(tenancy=self.tenancy, event_type=THSEventType.CARE_TICKET_OPENED).exists())

    def test_admin_can_advance_care_ticket_and_student_view_hides_internal_notes(self):
        ticket = CareTicket.objects.create(
            user=self.student,
            property=self.property,
            tenancy=self.tenancy,
            title="Door lock issue",
            description="Door lock needs attention.",
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"/api/core/care-tickets/{ticket.id}/",
            {
                "status": CareTicketStatus.RESOLVED,
                "student_safe_summary": "Door lock issue has been resolved.",
                "internal_notes": "Contractor confirmed repair.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.resolved_at)
        self.assertTrue(ticket.events.filter(event_type="RESOLVED").exists())
        self.assertTrue(TenancyHealthEvent.objects.filter(tenancy=self.tenancy, event_type=THSEventType.CARE_TICKET_RESOLVED).exists())

        self.client.force_authenticate(user=self.student)
        list_response = self.client.get("/api/core/me/care-tickets/")

        self.assertEqual(list_response.status_code, 200)
        self.assertNotIn("internal_notes", list_response.data[0])
        self.assertEqual(list_response.data[0]["student_safe_summary"], "Door lock issue has been resolved.")

    def test_landlord_can_see_visible_care_ticket_but_not_hidden_attachment(self):
        visible_ticket = CareTicket.objects.create(
            user=self.student,
            property=self.property,
            tenancy=self.tenancy,
            title="Sink leak",
            description="Sink leak visible to landlord.",
            landlord_visible=True,
        )
        hidden_ticket = CareTicket.objects.create(
            user=self.student,
            property=self.property,
            tenancy=self.tenancy,
            title="Private care note",
            description="Private operations-only care issue.",
            landlord_visible=False,
        )
        attachment = CareTicketAttachment.objects.create(
            ticket=visible_ticket,
            uploaded_by=self.student,
            file=SimpleUploadedFile("private.pdf", b"%PDF-1.4 private", content_type="application/pdf"),
            original_filename="private.pdf",
            content_type="application/pdf",
            file_size=16,
            landlord_visible=False,
        )

        self.client.force_authenticate(user=self.landlord)
        list_response = self.client.get("/api/core/landlord/care-tickets/")
        download_response = self.client.get(f"/api/core/care-attachments/{attachment.id}/download/")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(list_response.data[0]["id"], str(visible_ticket.id))
        self.assertNotEqual(list_response.data[0]["id"], str(hidden_ticket.id))
        self.assertEqual(download_response.status_code, 403)

@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class QuantumSupportRequestTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            "support-student@example.com",
            "Password123!",
            role=UserRole.STUDENT,
            full_name="Support Student",
        )
        self.other_student = User.objects.create_user(
            "support-other@example.com",
            "Password123!",
            role=UserRole.STUDENT,
            full_name="Other Student",
        )
        self.admin = User.objects.create_user(
            "support-admin@example.com",
            "Password123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        self.property = Property.objects.create(
            title="Support Test Studio",
            slug="support-test-studio",
            city="London",
            rent_monthly=900,
            status=PropertyStatus.APPROVED,
        )
        self.application = HousingApplication.objects.create(user=self.student, property=self.property)

    def test_student_can_create_support_request_with_timeline_and_notification(self):
        self.client.force_authenticate(user=self.student)

        response = self.client.post(
            "/api/core/me/support-requests/",
            {
                "application": str(self.application.id),
                "category": "BANKING_GUIDANCE",
                "priority": "MEDIUM",
                "title": "Need help opening UK bank account",
                "description": "Please guide me on acceptable documents.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        support_request = SupportRequest.objects.get(id=response.data["id"])
        self.assertEqual(support_request.status, SupportRequestStatus.OPEN)
        self.assertEqual(support_request.user, self.student)
        self.assertEqual(support_request.application, self.application)
        self.assertTrue(support_request.events.filter(event_type="CREATED").exists())
        self.assertTrue(Notification.objects.filter(user=self.student, title="Quantum Support update").exists())
        self.assertTrue(AuditLog.objects.filter(action="support_request.create").exists())

    def test_admin_can_resolve_support_request_and_student_view_hides_internal_notes(self):
        support_request = SupportRequest.objects.create(
            user=self.student,
            application=self.application,
            category="ATS_CV_SUPPORT",
            priority="HIGH",
            title="Need ATS CV review",
            description="Please help me prepare CV for UK part-time roles.",
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"/api/core/support-requests/{support_request.id}/",
            {
                "status": SupportRequestStatus.RESOLVED,
                "student_safe_summary": "CV support completed and shared with you.",
                "internal_notes": "Reviewed CV and marked service complete.",
                "assigned_to": str(self.admin.id),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        support_request.refresh_from_db()
        self.assertEqual(support_request.status, SupportRequestStatus.RESOLVED)
        self.assertIsNotNone(support_request.resolved_at)
        self.assertTrue(support_request.events.filter(event_type="RESOLVED").exists())
        self.assertTrue(AuditLog.objects.filter(action="support_request.update").exists())

        self.client.force_authenticate(user=self.student)
        list_response = self.client.get("/api/core/me/support-requests/")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data[0]["id"], str(support_request.id))
        self.assertNotIn("internal_notes", list_response.data[0])
        self.assertNotIn("assigned_to", list_response.data[0])
        self.assertNotIn("admin_message", list_response.data[0]["events"][0])

    def test_support_attachment_is_private_to_owner_and_staff(self):
        support_request = SupportRequest.objects.create(
            user=self.student,
            application=self.application,
            category="SETTLEMENT_SUPPORT",
            priority="LOW",
            title="Settlement checklist",
            description="Need checklist review.",
        )
        attachment = SupportRequestAttachment.objects.create(
            support_request=support_request,
            uploaded_by=self.student,
            file=SimpleUploadedFile("support.pdf", b"support-bytes", content_type="application/pdf"),
            original_filename="support.pdf",
            content_type="application/pdf",
            file_size=13,
        )

        self.client.force_authenticate(user=self.other_student)
        denied = self.client.get(f"/api/core/support-attachments/{attachment.id}/download/")
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(user=self.student)
        allowed = self.client.get(f"/api/core/support-attachments/{attachment.id}/download/")
        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="support_request_attachment.download").exists())

    def test_admin_support_intelligence_returns_rag_sources_without_openai(self):
        SupportRequest.objects.create(
            user=self.student,
            application=self.application,
            category="AIRPORT_PICKUP",
            priority="HIGH",
            title="Airport pickup timing",
            description="Student arrives at Heathrow terminal 3 with two suitcases.",
        )
        self.client.force_authenticate(user=self.admin)

        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            response = self.client.post(
                "/api/core/support-intelligence/",
                {"query": "airport pickup Heathrow luggage"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mode"], "rag")
        self.assertEqual(response.data["retrieval"], "lexical_operational_search")
        self.assertFalse(response.data["coverage"]["uses_openai"])
        self.assertGreaterEqual(response.data["coverage"]["source_count"], 1)
        self.assertIn("draft_reply", response.data)
        source_types = {source["source_type"] for source in response.data["sources"]}
        self.assertIn("support_request", source_types)

    def test_student_cannot_use_admin_support_intelligence(self):
        self.client.force_authenticate(user=self.student)

        response = self.client.post(
            "/api/core/support-intelligence/",
            {"query": "bank support"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)


class QuantumAssistReminderTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            "assist-student@example.com",
            "Password123!",
            role=UserRole.STUDENT,
            full_name="Assist Student",
        )
        self.admin = User.objects.create_user(
            "assist-admin@example.com",
            "Password123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        self.property = Property.objects.create(
            title="Assist Test Studio",
            slug="assist-test-studio",
            city="London",
            rent_monthly=900,
            status=PropertyStatus.APPROVED,
        )
        self.application = HousingApplication.objects.create(user=self.student, property=self.property)

    def test_admin_can_create_assist_reminder_with_automation_log(self):
        self.client.force_authenticate(user=self.admin)
        due_at = timezone.now() + timezone.timedelta(days=2)

        response = self.client.post(
            "/api/core/assist-reminders/",
            {
                "user": str(self.student.id),
                "application": str(self.application.id),
                "reminder_type": AssistReminderType.MOVE_IN,
                "priority": "HIGH",
                "title": "Prepare move-in checklist",
                "student_message": "Please complete your move-in checklist.",
                "internal_notes": "Confirm airport pickup timing.",
                "due_at": due_at.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        reminder = AssistReminder.objects.get(id=response.data["id"])
        self.assertEqual(reminder.status, AssistReminderStatus.SCHEDULED)
        self.assertEqual(reminder.created_by, self.admin)
        self.assertTrue(AssistAutomationLog.objects.filter(reminder=reminder, action="CREATED").exists())
        self.assertTrue(AuditLog.objects.filter(action="assist_reminder.create").exists())

    def test_due_processing_sends_notification_and_student_view_is_safe(self):
        reminder = AssistReminder.objects.create(
            user=self.student,
            application=self.application,
            created_by=self.admin,
            reminder_type=AssistReminderType.DOCUMENT_EXPIRY,
            priority="MEDIUM",
            title="Upload updated document",
            student_message="Please upload your updated document.",
            internal_notes="Passport expiry reminder.",
            due_at=timezone.now() - timezone.timedelta(minutes=5),
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.post("/api/core/assist-reminders/process-due/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["processed_count"], 1)
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, AssistReminderStatus.SENT)
        self.assertIsNotNone(reminder.sent_at)
        self.assertTrue(Notification.objects.filter(user=self.student, title="Quantum Assist reminder").exists())
        self.assertTrue(AssistAutomationLog.objects.filter(reminder=reminder, action="NOTIFICATION_SENT").exists())

        self.client.force_authenticate(user=self.student)
        list_response = self.client.get("/api/core/me/assist-reminders/")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data[0]["id"], str(reminder.id))
        self.assertNotIn("internal_notes", list_response.data[0])
        self.assertNotIn("metadata", list_response.data[0])
        self.assertNotIn("actor", list_response.data[0]["automation_logs"][0])

    def test_student_can_complete_own_assist_reminder(self):
        reminder = AssistReminder.objects.create(
            user=self.student,
            application=self.application,
            reminder_type=AssistReminderType.GENERAL,
            priority="LOW",
            title="Confirm support call",
            student_message="Please confirm your support call.",
            due_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.student)

        response = self.client.post(f"/api/core/me/assist-reminders/{reminder.id}/complete/")

        self.assertEqual(response.status_code, 200)
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, AssistReminderStatus.COMPLETED)
        self.assertIsNotNone(reminder.completed_at)
        self.assertTrue(AssistAutomationLog.objects.filter(reminder=reminder, action="COMPLETED").exists())
        self.assertTrue(AuditLog.objects.filter(action="assist_reminder.complete").exists())


class QuantumRolePermissionAuditTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            "role-student@example.com",
            "Password123!",
            role=UserRole.STUDENT,
        )
        self.other_student = User.objects.create_user(
            "role-other@example.com",
            "Password123!",
            role=UserRole.STUDENT,
        )
        self.landlord = User.objects.create_user(
            "role-landlord@example.com",
            "Password123!",
            role=UserRole.LANDLORD,
        )
        self.staff = User.objects.create_user(
            "role-staff@example.com",
            "Password123!",
            role=UserRole.STAFF,
            is_staff=True,
        )
        self.admin = User.objects.create_user(
            "role-admin@example.com",
            "Password123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        self.property = Property.objects.create(
            title="Role Audit Studio",
            slug="role-audit-studio",
            city="London",
            rent_monthly=900,
            assigned_landlord=self.landlord,
            status=PropertyStatus.APPROVED,
        )
        self.application = HousingApplication.objects.create(user=self.student, property=self.property)
        self.care_ticket = CareTicket.objects.create(
            user=self.student,
            property=self.property,
            application=self.application,
            title="Audit care ticket",
            description="Care permission audit.",
        )
        self.support_request = SupportRequest.objects.create(
            user=self.student,
            application=self.application,
            title="Audit support request",
            description="Support permission audit.",
        )
        self.assist_reminder = AssistReminder.objects.create(
            user=self.student,
            application=self.application,
            reminder_type=AssistReminderType.GENERAL,
            title="Audit reminder",
            student_message="Permission audit reminder.",
            due_at=timezone.now(),
        )

    def test_staff_can_read_but_not_write_operational_admin_workflows(self):
        self.client.force_authenticate(user=self.staff)

        self.assertEqual(self.client.get("/api/core/care-tickets/").status_code, 200)
        self.assertEqual(self.client.get("/api/core/support-requests/").status_code, 200)
        self.assertEqual(self.client.get("/api/core/assist-reminders/").status_code, 200)

        care_update = self.client.patch(
            f"/api/core/care-tickets/{self.care_ticket.id}/",
            {"status": CareTicketStatus.RESOLVED},
            format="json",
        )
        support_update = self.client.patch(
            f"/api/core/support-requests/{self.support_request.id}/",
            {"status": SupportRequestStatus.RESOLVED},
            format="json",
        )
        assist_update = self.client.patch(
            f"/api/core/assist-reminders/{self.assist_reminder.id}/",
            {"status": AssistReminderStatus.CANCELLED},
            format="json",
        )
        process_due = self.client.post("/api/core/assist-reminders/process-due/")

        self.assertEqual(care_update.status_code, 403)
        self.assertEqual(support_update.status_code, 403)
        self.assertEqual(assist_update.status_code, 403)
        self.assertEqual(process_due.status_code, 403)

    def test_admin_can_write_operational_workflows(self):
        self.client.force_authenticate(user=self.admin)

        care_update = self.client.patch(
            f"/api/core/care-tickets/{self.care_ticket.id}/",
            {"status": CareTicketStatus.RESOLVED, "student_safe_summary": "Care resolved."},
            format="json",
        )
        support_update = self.client.patch(
            f"/api/core/support-requests/{self.support_request.id}/",
            {"status": SupportRequestStatus.RESOLVED, "student_safe_summary": "Support resolved."},
            format="json",
        )
        assist_update = self.client.patch(
            f"/api/core/assist-reminders/{self.assist_reminder.id}/",
            {"status": AssistReminderStatus.CANCELLED},
            format="json",
        )
        process_due = self.client.post("/api/core/assist-reminders/process-due/")

        self.assertEqual(care_update.status_code, 200)
        self.assertEqual(support_update.status_code, 200)
        self.assertEqual(assist_update.status_code, 200)
        self.assertEqual(process_due.status_code, 200)

    def test_student_and_landlord_cannot_read_admin_operational_endpoints(self):
        for user in [self.student, self.landlord]:
            self.client.force_authenticate(user=user)
            self.assertEqual(self.client.get("/api/core/care-tickets/").status_code, 403)
            self.assertEqual(self.client.get("/api/core/support-requests/").status_code, 403)
            self.assertEqual(self.client.get("/api/core/assist-reminders/").status_code, 403)

    def test_students_cannot_cross_read_other_student_workflows(self):
        self.client.force_authenticate(user=self.other_student)

        self.assertEqual(self.client.get("/api/core/me/care-tickets/").status_code, 200)
        self.assertEqual(self.client.get("/api/core/me/support-requests/").status_code, 200)
        self.assertEqual(self.client.get("/api/core/me/assist-reminders/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/core/me/assist-reminders/{self.assist_reminder.id}/complete/").status_code, 404)

        self.assertEqual(self.client.get("/api/core/me/care-tickets/").data, [])
        self.assertEqual(self.client.get("/api/core/me/support-requests/").data, [])
        self.assertEqual(self.client.get("/api/core/me/assist-reminders/").data, [])


class ProductionReportingAnalyticsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            "report-student@example.com",
            "Password123!",
            role=UserRole.STUDENT,
        )
        self.landlord = User.objects.create_user(
            "report-landlord@example.com",
            "Password123!",
            role=UserRole.LANDLORD,
        )
        self.staff = User.objects.create_user(
            "report-staff@example.com",
            "Password123!",
            role=UserRole.STAFF,
            is_staff=True,
        )
        self.admin = User.objects.create_user(
            "report-admin@example.com",
            "Password123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        self.property = Property.objects.create(
            title="Reporting Studio",
            slug="reporting-studio",
            city="London",
            rent_monthly=1000,
            assigned_landlord=self.landlord,
            status=PropertyStatus.APPROVED,
        )
        self.application = HousingApplication.objects.create(
            user=self.student,
            property=self.property,
            entry_status=ApplicationEntryStatus.RETURNED,
            stage=ApplicationStage.MATCHING,
        )
        self.tenancy = Tenancy.objects.create(
            user=self.student,
            property=self.property,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timezone.timedelta(days=45),
            rent_amount=1000,
            status=TenancyStatus.ACTIVE,
        )
        refresh_tenancy_health_score(self.tenancy)
        PropMatchResult.objects.create(
            user=self.student,
            property=self.property,
            rank=1,
            confidence_score=86,
            budget_pass=True,
            availability_pass=True,
            isra_pass=True,
            eligible=True,
        )
        CareTicket.objects.create(
            user=self.student,
            property=self.property,
            tenancy=self.tenancy,
            application=self.application,
            title="Urgent care report",
            description="Reporting care signal.",
            priority=CareTicketPriority.URGENT,
        )
        SupportRequest.objects.create(
            user=self.student,
            application=self.application,
            title="Urgent support report",
            description="Reporting support signal.",
            priority=SupportRequestPriority.URGENT,
        )
        AssistReminder.objects.create(
            user=self.student,
            application=self.application,
            reminder_type=AssistReminderType.MOVE_IN,
            title="Due report reminder",
            student_message="Due report reminder.",
            due_at=timezone.now() - timezone.timedelta(hours=1),
        )
        StudentDocument.objects.create(
            user=self.student,
            application=self.application,
            document_type=StudentDocumentType.PASSPORT,
            original_filename="passport.pdf",
            file="student-documents/report/passport.pdf",
            verification_status=VerificationState.PENDING,
        )
        YOEMetric.objects.create(
            property=self.property,
            landlord=self.landlord,
            property_value=100000,
            annual_rent=12000,
            annual_expenses=1000,
            occupancy_rate=91.25,
            gross_yield=12,
            net_yield=11,
            rent_collection_rate=98.5,
            active_tenancies=1,
            open_complaints=0,
        )

    def test_admin_production_report_returns_operational_sections(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/core/reports/production/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("summary", response.data)
        self.assertIn("distributions", response.data)
        self.assertIn("operations", response.data)
        self.assertIn("risks", response.data)
        self.assertEqual(response.data["summary"]["total_students"], 1)
        self.assertEqual(response.data["summary"]["total_landlords"], 1)
        self.assertEqual(response.data["summary"]["active_tenancies"], 1)
        self.assertEqual(response.data["operations"]["care"]["urgent_open"], 1)
        self.assertEqual(response.data["operations"]["support"]["urgent_open"], 1)
        self.assertEqual(response.data["operations"]["assist"]["due"], 1)
        self.assertEqual(response.data["operations"]["documents"]["pending_or_resubmission"], 1)
        self.assertEqual(response.data["quantum_match"]["eligible_results"], 1)
        self.assertEqual(response.data["occupancy"]["avg_occupancy_rate"], 91.25)

    def test_staff_can_read_production_report(self):
        self.client.force_authenticate(user=self.staff)

        response = self.client.get("/api/core/reports/production/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("generated_at", response.data)

    def test_student_and_landlord_cannot_read_production_report(self):
        for user in [self.student, self.landlord]:
            self.client.force_authenticate(user=user)
            self.assertEqual(self.client.get("/api/core/reports/production/").status_code, 403)


class ProductionMonitoringTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            "monitor-student@example.com",
            "Password123!",
            role=UserRole.STUDENT,
        )
        self.landlord = User.objects.create_user(
            "monitor-landlord@example.com",
            "Password123!",
            role=UserRole.LANDLORD,
        )
        self.staff = User.objects.create_user(
            "monitor-staff@example.com",
            "Password123!",
            role=UserRole.STAFF,
            is_staff=True,
        )
        self.admin = User.objects.create_user(
            "monitor-admin@example.com",
            "Password123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )

    def test_admin_monitoring_status_returns_production_checks(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/core/monitoring/production/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(response.data["overall_status"], ["ok", "warning", "error"])
        self.assertIn("checks", response.data)
        self.assertIn("audit_activity", response.data)
        self.assertIn("runtime", response.data)
        check_names = {row["name"] for row in response.data["checks"]}
        self.assertIn("Database", check_names)
        self.assertIn("Migrations", check_names)
        self.assertIn("Error Tracking", check_names)
        self.assertIn("Backups", check_names)
        self.assertIn("Disk Space", check_names)

    def test_staff_can_read_monitoring_status(self):
        self.client.force_authenticate(user=self.staff)

        response = self.client.get("/api/core/monitoring/production/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("generated_at", response.data)

    def test_student_and_landlord_cannot_read_monitoring_status(self):
        for user in [self.student, self.landlord]:
            self.client.force_authenticate(user=user)
            self.assertEqual(self.client.get("/api/core/monitoring/production/").status_code, 403)


class QuantumFlowApplicationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            "flow-student@example.com",
            "Password123!",
            role=UserRole.STUDENT,
        )
        self.admin = User.objects.create_user(
            "flow-admin@example.com",
            "Password123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        self.property = Property.objects.create(
            title="Flow Test Studio",
            slug="flow-test-studio",
            city="London",
            rent_monthly=900,
            status=PropertyStatus.APPROVED,
        )
        IntentForm.objects.create(
            user=self.student,
            room_type="Studio",
            budget_min=700,
            budget_max=950,
            city="London",
            preferred_locality="Bloomsbury",
            university="UCL",
            nationality="India",
            move_in_date=timezone.now().date() + timezone.timedelta(days=45),
        )

    def test_student_can_create_and_view_application_lifecycle(self):
        self.client.force_authenticate(user=self.student)

        create_response = self.client.post(
            "/api/core/me/applications/",
            {
                "property": str(self.property.id),
                "applicant_notes": "Need a verified studio near campus.",
            },
            format="json",
        )
        list_response = self.client.get("/api/core/me/applications/")

        self.assertEqual(create_response.status_code, 201)
        self.assertTrue(create_response.data["application_code"].startswith("QL-"))
        self.assertEqual(create_response.data["entry_status"], ApplicationEntryStatus.SUBMITTED)
        self.assertEqual(create_response.data["entry_status_label"], "Submitted")
        self.assertEqual(create_response.data["intake_source"], "STUDENT_PORTAL")
        self.assertEqual(create_response.data["applicant_notes"], "Need a verified studio near campus.")
        self.assertEqual(create_response.data["intake_snapshot"]["city"], "London")
        self.assertEqual(create_response.data["intake_snapshot"]["university"], "UCL")
        self.assertGreaterEqual(create_response.data["intake_completeness"]["percent"], 80)
        self.assertIsNotNone(create_response.data["submitted_at"])
        self.assertEqual(create_response.data["stage"], ApplicationStage.APPLICATION)
        self.assertEqual(create_response.data["stage_label"], "Application")
        self.assertEqual(create_response.data["progress_index"], 1)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
        self.assertTrue(ApplicationTimelineEvent.objects.filter(application_id=create_response.data["id"], event_type="APPLICATION_SUBMITTED").exists())
        self.assertTrue(Notification.objects.filter(user=self.student, title="Quantum Flow update").exists())
        self.assertTrue(AuditLog.objects.filter(action="housing_application.create").exists())

    def test_admin_can_advance_application_stage_with_history(self):
        application = HousingApplication.objects.create(
            user=self.student,
            property=self.property,
            next_action="Confirm student intent and required details.",
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"/api/core/applications/{application.id}/",
            {
                "stage": ApplicationStage.VERIFICATION,
                "entry_status": ApplicationEntryStatus.READY,
                "stage_notes": "Documents received.",
                "admin_entry_notes": "Entry intake complete.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.stage, ApplicationStage.VERIFICATION)
        self.assertEqual(application.entry_status, ApplicationEntryStatus.READY)
        self.assertIsNotNone(application.entry_reviewed_at)
        self.assertEqual(application.admin_entry_notes, "Entry intake complete.")
        self.assertEqual(application.stage_history[-1]["from"], ApplicationStage.APPLICATION)
        self.assertEqual(application.stage_history[-1]["to"], ApplicationStage.VERIFICATION)
        self.assertIn("Review identity", application.next_action)
        self.assertTrue(
            ApplicationTimelineEvent.objects.filter(
                application=application,
                from_stage=ApplicationStage.APPLICATION,
                to_stage=ApplicationStage.VERIFICATION,
            ).exists()
        )
        self.assertTrue(Notification.objects.filter(user=self.student, application=application).exists())
        self.assertTrue(AuditLog.objects.filter(action="housing_application.update").exists())

    def test_student_timeline_hides_admin_metadata(self):
        application = HousingApplication.objects.create(user=self.student, property=self.property)
        self.client.force_authenticate(user=self.admin)
        self.client.patch(
            f"/api/core/applications/{application.id}/",
            {"stage": ApplicationStage.MATCHING, "stage_notes": "Internal matching review."},
            format="json",
        )

        self.client.force_authenticate(user=self.student)
        timeline_response = self.client.get("/api/core/me/application-timeline/")
        notification_response = self.client.get("/api/core/me/notifications/")

        self.assertEqual(timeline_response.status_code, 200)
        self.assertEqual(notification_response.status_code, 200)
        self.assertNotIn("admin_message", timeline_response.data[0])
        self.assertNotIn("metadata", timeline_response.data[0])
        self.assertEqual(notification_response.data[0]["title"], "Quantum Flow update")

    def test_student_cannot_read_admin_applications(self):
        self.client.force_authenticate(user=self.student)

        response = self.client.get("/api/core/applications/")

        self.assertEqual(response.status_code, 403)


class VerifiedTenancyRecordTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            "record-student@example.com",
            "Password123!",
            role=UserRole.STUDENT,
        )
        self.property = Property.objects.create(
            title="Record Test Studio",
            slug="record-test-studio",
            city="London",
            rent_monthly=900,
            status=PropertyStatus.APPROVED,
        )

    def test_completed_clean_tenancy_creates_privacy_safe_record(self):
        today = timezone.now().date()
        tenancy = Tenancy.objects.create(
            user=self.student,
            property=self.property,
            start_date=today - timezone.timedelta(days=180),
            end_date=today,
            rent_amount=900,
            status=TenancyStatus.ENDED,
        )

        refresh_tenancy_health_score(tenancy)
        record = TenancyRecord.objects.get(tenancy=tenancy)

        self.assertEqual(record.badge_label, "Verified Tenancy Completion")
        self.assertEqual(record.outcome, "Successful occupancy completed")

        self.client.force_authenticate(user=self.student)
        response = self.client.get("/api/core/me/tenancy-records/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["includes"][0], "tenancy completion status")
        self.assertIn("raw complaint narratives", response.data[0]["excludes"])
        self.assertIn("without exposing sensitive", response.data[0]["privacy_statement"])
