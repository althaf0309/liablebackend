import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User, UserRole

from .models import (
    AuditLog,
    Complaint,
    ComplaintAttachment,
    ApplicationStage,
    HousingApplication,
    ISRAscore,
    RentLedger,
    RentLedgerStatus,
    Property,
    PropertyStatus,
    StudentDocument,
    StudentDocumentType,
    Tenancy,
    TenancyRecord,
    TenancyStatus,
)
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

    def test_student_can_create_and_view_application_lifecycle(self):
        self.client.force_authenticate(user=self.student)

        create_response = self.client.post(
            "/api/core/me/applications/",
            {"property": str(self.property.id)},
            format="json",
        )
        list_response = self.client.get("/api/core/me/applications/")

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data["stage"], ApplicationStage.APPLICATION)
        self.assertEqual(create_response.data["stage_label"], "Application")
        self.assertEqual(create_response.data["progress_index"], 1)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
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
                "stage_notes": "Documents received.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.stage, ApplicationStage.VERIFICATION)
        self.assertEqual(application.stage_history[-1]["from"], ApplicationStage.APPLICATION)
        self.assertEqual(application.stage_history[-1]["to"], ApplicationStage.VERIFICATION)
        self.assertIn("Review identity", application.next_action)
        self.assertTrue(AuditLog.objects.filter(action="housing_application.update").exists())

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
