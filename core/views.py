from django.db import connection
from django.db.models import Q
from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from rest_framework.generics import CreateAPIView, ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .engines import calculate_isra_for_user, run_propmatch_for_user
from .models import *
from .serializers import *
from .audit import write_audit_log
from .assist import update_assist_reminder_status
from .care import create_care_event
from .document_verification import refresh_application_verification_state, refresh_user_open_applications
from .quantum_flow import create_application_for_user
from .support import create_support_event
from .throttles import ContactCreateRateThrottle
from .tenancy_intelligence import refresh_tenancy_health_score


ALLOWED_PRIVATE_UPLOAD_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}
MAX_PRIVATE_UPLOAD_BYTES = 5 * 1024 * 1024


def validate_private_upload(uploaded_file):
    if uploaded_file.size > MAX_PRIVATE_UPLOAD_BYTES:
        return "File must be 5 MB or smaller."
    if uploaded_file.content_type not in ALLOWED_PRIVATE_UPLOAD_TYPES:
        return "Only PDF, JPG, PNG, and WEBP files are allowed."
    return ""


def _pdf_escape(value):
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_ptr_certificate_pdf(record):
    period = f"{record.tenancy.start_date.isoformat()} to {record.tenancy.end_date.isoformat()}"
    student_name = record.user.full_name or record.user.email
    lines = [
        ("Liable Group Services Ltd", 18),
        ("Verified Tenancy Record Certificate", 16),
        (record.badge_label, 14),
        (f"Student: {student_name}", 11),
        (f"Property: {record.property.title}", 11),
        (f"Tenancy Period: {period}", 11),
        (f"Outcome: {record.outcome}", 11),
        (f"THS Snapshot: {record.ths_score_snapshot} / 100", 11),
        (f"Certificate Code: {record.certificate_code}", 11),
        (f"Issued: {record.issued_at.date().isoformat()}", 11),
        ("Privacy Note: This certificate confirms successful occupancy history without exposing private documents, immigration details, sensitive financial evidence, raw complaint narratives, or raw scoring factors.", 9),
        ("Operational Note: This student completion record is separate from the Property Trust Record, which evaluates property-side reliability.", 9),
    ]
    text_ops = [
        "0.05 0.17 0.21 rg",
        "48 48 499 746 re f",
        "1 1 1 rg",
        "58 58 479 726 re f",
        "0.05 0.17 0.21 RG",
        "1.5 w",
        "70 70 455 700 re S",
        "BT",
        "0.05 0.17 0.21 rg",
        "72 742 Td",
    ]
    first = True
    for line, font_size in lines:
        if first:
            text_ops.extend([f"/F1 {font_size} Tf", f"({_pdf_escape(line)}) Tj"])
            first = False
        else:
            text_ops.extend([f"/F1 {font_size} Tf", "0 -38 Td", f"({_pdf_escape(line)}) Tj"])
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_at = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii"))
    return bytes(pdf)


class PublicPropertyListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicPropertyListSerializer

    def get_queryset(self):
        qs = (
            Property.objects
            .filter(status=PropertyStatus.APPROVED)
            .prefetch_related("images")
            .order_by("-is_featured", "-priority_rank", "-created_at")
        )

        q = (self.request.query_params.get("q") or "").strip()
        ptype = (self.request.query_params.get("type") or "").strip()
        city = (self.request.query_params.get("city") or "").strip()
        locality = (self.request.query_params.get("locality") or "").strip()
        min_rent = (self.request.query_params.get("min_rent") or "").strip()
        max_rent = (self.request.query_params.get("max_rent") or "").strip()
        bedrooms = (self.request.query_params.get("bedrooms") or "").strip()

        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(city__icontains=q)
                | Q(locality__icontains=q)
                | Q(description__icontains=q)
            )

        if city:
            qs = qs.filter(city__icontains=city)

        if locality:
            qs = qs.filter(locality__icontains=locality)

        if ptype:
            qs = qs.filter(property_type=str(ptype).upper())

        if bedrooms:
            try:
                count = int(bedrooms)
                qs = qs.filter(bedrooms__gte=4) if count >= 4 else qs.filter(bedrooms=count)
            except ValueError:
                pass

        if min_rent:
            try:
                qs = qs.filter(rent_monthly__gte=min_rent)
            except Exception:
                pass

        if max_rent:
            try:
                qs = qs.filter(rent_monthly__lte=max_rent)
            except Exception:
                pass

        return qs


class PublicPropertyDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicPropertyDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return (
            Property.objects
            .filter(status=PropertyStatus.APPROVED)
            .prefetch_related("images", "videos")
        )


class PublicBlogListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicBlogListSerializer

    def get_queryset(self):
        return (
            BlogPost.objects
            .filter(is_published=True)
            .order_by("-published_at", "-created_at")
        )


class PublicBlogDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicBlogDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return BlogPost.objects.filter(is_published=True)


class HealthCheckView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        checks = {"app": "ok", "database": "unknown"}
        http_status = status.HTTP_200_OK
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(checks, status=http_status)


@method_decorator(csrf_protect, name="dispatch")
class PublicContactCreateView(CreateAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = ContactMessageCreateSerializer
    queryset = ContactMessage.objects.all()
    throttle_classes = [ContactCreateRateThrottle]


class MyIntentFormView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        intent = getattr(request.user, "intent_form", None)
        if not intent:
            return Response({"detail": "Intent form not submitted"}, status=404)
        return Response(IntentFormSerializer(intent).data)

    def post(self, request):
        intent = getattr(request.user, "intent_form", None)
        serializer = IntentFormSerializer(instance=intent, data={**request.data, "user": request.user.id})
        serializer.is_valid(raise_exception=True)
        intent = serializer.save(user=request.user)
        score = calculate_isra_for_user(request.user)
        matches = run_propmatch_for_user(request.user)
        return Response(
            {
                "intent": IntentFormSerializer(intent).data,
                "isra_score": ISRAscoreSerializer(score).data,
                "matches": PropMatchResultSerializer(matches, many=True).data,
            }
        )


class MyISRAscoreView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        score = getattr(request.user, "isra_score", None)
        if not score:
            score = calculate_isra_for_user(request.user)
        return Response(StudentISRAsummarySerializer(score).data)


class MyPropMatchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PropMatchResult.objects.filter(user=request.user).select_related("property").prefetch_related("property__images")
        if not qs.exists() and hasattr(request.user, "intent_form"):
            run_propmatch_for_user(request.user)
            qs = PropMatchResult.objects.filter(user=request.user).select_related("property").prefetch_related("property__images")
        return Response(PropMatchResultSerializer(qs, many=True).data)

    def post(self, request):
        if not hasattr(request.user, "isra_score"):
            calculate_isra_for_user(request.user)
        results = run_propmatch_for_user(request.user)
        return Response(PropMatchResultSerializer(results, many=True).data)


class MyHousingApplicationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        applications = (
            HousingApplication.objects
            .filter(user=request.user)
            .select_related("property", "prop_match", "user")
            .order_by("-updated_at")
        )
        return Response(HousingApplicationSerializer(applications, many=True).data)

    def post(self, request):
        property_id = request.data.get("property")
        match_id = request.data.get("prop_match")
        applicant_notes = (request.data.get("applicant_notes") or "").strip()
        intake_snapshot = request.data.get("intake_snapshot")
        if intake_snapshot is not None and not isinstance(intake_snapshot, dict):
            return Response({"detail": "intake_snapshot must be an object."}, status=status.HTTP_400_BAD_REQUEST)
        property_obj = Property.objects.filter(id=property_id).first() if property_id else None
        prop_match = PropMatchResult.objects.filter(id=match_id, user=request.user).first() if match_id else None
        if match_id and not prop_match:
            return Response({"detail": "PropMatch result not found"}, status=status.HTTP_404_NOT_FOUND)
        if prop_match and not property_obj:
            property_obj = prop_match.property
        application = create_application_for_user(
            request.user,
            property_obj=property_obj,
            prop_match=prop_match,
            target_move_in_date=request.data.get("target_move_in_date") or None,
            applicant_notes=applicant_notes,
            intake_snapshot=intake_snapshot,
        )
        write_audit_log(
            request,
            "housing_application.create",
            application,
            {
                "stage": application.stage,
                "entry_status": application.entry_status,
                "intake_source": application.intake_source,
            },
        )
        return Response(HousingApplicationSerializer(application).data, status=status.HTTP_201_CREATED)


class MyApplicationTimelineListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ApplicationTimelineEventSerializer

    def get_queryset(self):
        return (
            ApplicationTimelineEvent.objects
            .filter(application__user=self.request.user)
            .select_related("application", "actor")
            .order_by("created_at")
        )


class MyNotificationListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).select_related("application", "timeline_event").order_by("-created_at")


class MyAssistReminderListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AssistReminderSerializer

    def get_queryset(self):
        return (
            AssistReminder.objects
            .filter(user=self.request.user)
            .select_related("application", "tenancy", "care_ticket", "support_request", "created_by", "assigned_to")
            .prefetch_related("automation_logs")
            .order_by("due_at", "-created_at")
        )


class MyAssistReminderCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        reminder = AssistReminder.objects.filter(id=id, user=request.user).first()
        if not reminder:
            return Response({"detail": "Assist reminder not found"}, status=status.HTTP_404_NOT_FOUND)
        update_assist_reminder_status(reminder, AssistReminderStatus.COMPLETED, actor=request.user)
        write_audit_log(request, "assist_reminder.complete", reminder, {"status": reminder.status})
        return Response(AssistReminderSerializer(reminder, context={"request": request}).data, status=status.HTTP_200_OK)


class MyTenancyListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TenancySerializer

    def get_queryset(self):
        return Tenancy.objects.filter(user=self.request.user).select_related("property").order_by("-start_date")


class MyRentLedgerListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RentLedgerSerializer

    def get_queryset(self):
        return (
            RentLedger.objects
            .filter(tenancy__user=self.request.user)
            .select_related("tenancy", "tenancy__property", "tenancy__user")
            .order_by("-due_date")
        )


class MyTenancyExtensionRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        tenancy = Tenancy.objects.filter(id=id, user=request.user).first()
        if not tenancy:
            return Response({"detail": "Tenancy not found"}, status=status.HTTP_404_NOT_FOUND)
        tenancy.extension_requested = True
        tenancy.save(update_fields=["extension_requested", "updated_at"])
        refresh_tenancy_health_score(tenancy)
        return Response(TenancySerializer(tenancy).data, status=status.HTTP_200_OK)


class MyTenancyHealthListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TenancyHealthScoreSerializer

    def get_queryset(self):
        for tenancy in Tenancy.objects.filter(user=self.request.user):
            refresh_tenancy_health_score(tenancy)
        return (
            TenancyHealthScore.objects
            .filter(tenancy__user=self.request.user)
            .select_related("tenancy", "tenancy__property", "tenancy__user")
            .prefetch_related("tenancy__health_events")
            .order_by("-updated_at")
        )


class MyTenancyRecordListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TenancyRecordSerializer

    def get_queryset(self):
        return TenancyRecord.objects.filter(user=self.request.user).select_related("property", "user", "tenancy").order_by("-issued_at")


class TenancyRecordCertificateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        record = TenancyRecord.objects.filter(id=id).select_related("user", "property", "tenancy").first()
        if not record:
            return Response({"detail": "Record not found"}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role not in ["ADMIN", "STAFF"] and record.user_id != request.user.id:
            return Response({"detail": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)
        response = HttpResponse(build_ptr_certificate_pdf(record), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{record.certificate_code}.pdf"'
        return response


class MyComplaintListCreateView(CreateAPIView, ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ComplaintSerializer

    def get_queryset(self):
        return Complaint.objects.filter(user=self.request.user).select_related("property").order_by("-created_at")

    def perform_create(self, serializer):
        complaint = serializer.save(user=self.request.user)
        tenancy = Tenancy.objects.filter(user=self.request.user, property=complaint.property).order_by("-start_date").first()
        if tenancy:
            refresh_tenancy_health_score(tenancy)


class MyStudentDocumentListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        if request.user.role != "STUDENT":
            return Response({"detail": "Student role required"}, status=status.HTTP_403_FORBIDDEN)
        documents = StudentDocument.objects.filter(user=request.user).order_by("-uploaded_at")
        return Response(StudentDocumentSerializer(documents, many=True).data)

    def post(self, request):
        if request.user.role != "STUDENT":
            return Response({"detail": "Student role required"}, status=status.HTTP_403_FORBIDDEN)
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"detail": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
        error = validate_private_upload(uploaded_file)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
        application = None
        application_id = request.data.get("application")
        if application_id:
            application = HousingApplication.objects.filter(id=application_id, user=request.user).first()
            if not application:
                return Response({"detail": "Application not found"}, status=status.HTTP_404_NOT_FOUND)
        expiry_date = None
        expiry_raw = (request.data.get("expiry_date") or "").strip()
        if expiry_raw:
            expiry_date = parse_date(expiry_raw)
            if not expiry_date:
                return Response({"detail": "expiry_date must use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        document = StudentDocument.objects.create(
            user=request.user,
            application=application,
            document_type=request.data.get("document_type") or StudentDocumentType.OTHER,
            requirement_stage=request.data.get("requirement_stage") or DocumentRequirementStage.VERIFICATION,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            content_type=uploaded_file.content_type or "",
            file_size=uploaded_file.size,
            expiry_date=expiry_date,
        )
        if application:
            refresh_application_verification_state(application)
        else:
            refresh_user_open_applications(request.user)
        write_audit_log(
            request,
            "student_document.upload",
            document,
            {
                "application_id": str(application.id) if application else None,
                "document_type": document.document_type,
                "requirement_stage": document.requirement_stage,
                "content_type": document.content_type,
                "file_size": document.file_size,
                "expiry_date": expiry_raw or None,
            },
        )
        return Response(StudentDocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class MyComplaintAttachmentCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, id):
        complaint = Complaint.objects.filter(id=id, user=request.user).first()
        if not complaint:
            return Response({"detail": "Complaint not found"}, status=status.HTTP_404_NOT_FOUND)
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"detail": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
        error = validate_private_upload(uploaded_file)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        attachment = ComplaintAttachment.objects.create(
            complaint=complaint,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            content_type=uploaded_file.content_type or "",
            file_size=uploaded_file.size,
        )
        write_audit_log(
            request,
            "complaint_attachment.upload",
            attachment,
            {
                "complaint_id": str(complaint.id),
                "content_type": attachment.content_type,
                "file_size": attachment.file_size,
            },
        )
        return Response(ComplaintAttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)


class MyCareTicketListCreateView(CreateAPIView, ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CareTicketSerializer

    def get_queryset(self):
        return (
            CareTicket.objects
            .filter(user=self.request.user)
            .select_related("property", "tenancy", "application", "assigned_to", "user")
            .prefetch_related("events", "attachments")
            .order_by("-updated_at")
        )

    def perform_create(self, serializer):
        ticket = serializer.save(user=self.request.user, status=CareTicketStatus.OPEN, internal_notes="", assigned_to=None)
        if not ticket.tenancy_id:
            ticket.tenancy = Tenancy.objects.filter(user=self.request.user, property=ticket.property, status=TenancyStatus.ACTIVE).order_by("-start_date").first()
            if ticket.tenancy_id:
                ticket.save(update_fields=["tenancy", "updated_at"])
        create_care_event(ticket, actor=self.request.user)
        write_audit_log(
            self.request,
            "care_ticket.create",
            ticket,
            {
                "property_id": str(ticket.property_id),
                "category": ticket.category,
                "priority": ticket.priority,
                "status": ticket.status,
            },
        )


class MyCareTicketAttachmentCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, id):
        ticket = CareTicket.objects.filter(id=id, user=request.user).first()
        if not ticket:
            return Response({"detail": "Care ticket not found"}, status=status.HTTP_404_NOT_FOUND)
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"detail": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
        error = validate_private_upload(uploaded_file)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
        attachment = CareTicketAttachment.objects.create(
            ticket=ticket,
            uploaded_by=request.user,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            content_type=uploaded_file.content_type or "",
            file_size=uploaded_file.size,
            landlord_visible=str(request.data.get("landlord_visible", "true")).lower() != "false",
        )
        write_audit_log(
            request,
            "care_ticket_attachment.upload",
            attachment,
            {
                "ticket_id": str(ticket.id),
                "content_type": attachment.content_type,
                "file_size": attachment.file_size,
                "landlord_visible": attachment.landlord_visible,
            },
        )
        return Response(CareTicketAttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)


class MySupportRequestListCreateView(CreateAPIView, ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportRequestSerializer

    def get_queryset(self):
        return (
            SupportRequest.objects
            .filter(user=self.request.user)
            .select_related("application", "assigned_to", "user")
            .prefetch_related("events", "attachments")
            .order_by("-updated_at")
        )

    def perform_create(self, serializer):
        application = serializer.validated_data.get("application")
        if application and application.user_id != self.request.user.id:
            raise serializers.ValidationError({"application": "Application not found."})
        support_request = serializer.save(
            user=self.request.user,
            status=SupportRequestStatus.OPEN,
            internal_notes="",
            assigned_to=None,
            partner_visible=False,
        )
        create_support_event(support_request, actor=self.request.user)
        write_audit_log(
            self.request,
            "support_request.create",
            support_request,
            {
                "application_id": str(support_request.application_id) if support_request.application_id else None,
                "category": support_request.category,
                "priority": support_request.priority,
                "status": support_request.status,
            },
        )


class MySupportRequestAttachmentCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, id):
        support_request = SupportRequest.objects.filter(id=id, user=request.user).first()
        if not support_request:
            return Response({"detail": "Support request not found"}, status=status.HTTP_404_NOT_FOUND)
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"detail": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
        error = validate_private_upload(uploaded_file)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
        attachment = SupportRequestAttachment.objects.create(
            support_request=support_request,
            uploaded_by=request.user,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            content_type=uploaded_file.content_type or "",
            file_size=uploaded_file.size,
            partner_visible=str(request.data.get("partner_visible", "false")).lower() == "true",
        )
        write_audit_log(
            request,
            "support_request_attachment.upload",
            attachment,
            {
                "support_request_id": str(support_request.id),
                "content_type": attachment.content_type,
                "file_size": attachment.file_size,
                "partner_visible": attachment.partner_visible,
            },
        )
        return Response(SupportRequestAttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)


class PrivateStudentDocumentDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        document = StudentDocument.objects.filter(id=id).select_related("user").first()
        if not document:
            return Response({"detail": "Document not found"}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role not in ["ADMIN", "STAFF"] and document.user_id != request.user.id:
            return Response({"detail": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)
        write_audit_log(
            request,
            "student_document.download",
            document,
            {
                "document_owner_id": str(document.user_id),
                "document_type": document.document_type,
                "content_type": document.content_type,
                "file_size": document.file_size,
            },
        )
        return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.original_filename)


class PrivateComplaintAttachmentDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        attachment = ComplaintAttachment.objects.filter(id=id).select_related("complaint", "complaint__property").first()
        if not attachment:
            return Response({"detail": "Attachment not found"}, status=status.HTTP_404_NOT_FOUND)
        allowed = request.user.role in ["ADMIN", "STAFF"] or attachment.complaint.user_id == request.user.id
        if not allowed:
            return Response({"detail": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)
        write_audit_log(
            request,
            "complaint_attachment.download",
            attachment,
            {
                "complaint_id": str(attachment.complaint_id),
                "complaint_owner_id": str(attachment.complaint.user_id),
                "content_type": attachment.content_type,
                "file_size": attachment.file_size,
            },
        )
        return FileResponse(attachment.file.open("rb"), as_attachment=True, filename=attachment.original_filename)


class PrivateCareTicketAttachmentDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        attachment = CareTicketAttachment.objects.filter(id=id).select_related("ticket", "ticket__property").first()
        if not attachment:
            return Response({"detail": "Attachment not found"}, status=status.HTTP_404_NOT_FOUND)
        is_admin = request.user.role in ["ADMIN", "STAFF"]
        is_owner = attachment.ticket.user_id == request.user.id
        is_landlord = (
            request.user.role == "LANDLORD"
            and attachment.landlord_visible
            and attachment.ticket.landlord_visible
            and attachment.ticket.property.assigned_landlord_id == request.user.id
        )
        if not (is_admin or is_owner or is_landlord):
            return Response({"detail": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)
        write_audit_log(
            request,
            "care_ticket_attachment.download",
            attachment,
            {
                "ticket_id": str(attachment.ticket_id),
                "ticket_owner_id": str(attachment.ticket.user_id),
                "content_type": attachment.content_type,
                "file_size": attachment.file_size,
            },
        )
        return FileResponse(attachment.file.open("rb"), as_attachment=True, filename=attachment.original_filename)


class PrivateSupportRequestAttachmentDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        attachment = SupportRequestAttachment.objects.filter(id=id).select_related("support_request").first()
        if not attachment:
            return Response({"detail": "Attachment not found"}, status=status.HTTP_404_NOT_FOUND)
        is_admin = request.user.role in ["ADMIN", "STAFF"]
        is_owner = attachment.support_request.user_id == request.user.id
        if not (is_admin or is_owner):
            return Response({"detail": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)
        write_audit_log(
            request,
            "support_request_attachment.download",
            attachment,
            {
                "support_request_id": str(attachment.support_request_id),
                "support_request_owner_id": str(attachment.support_request.user_id),
                "content_type": attachment.content_type,
                "file_size": attachment.file_size,
            },
        )
        return FileResponse(attachment.file.open("rb"), as_attachment=True, filename=attachment.original_filename)


class LandlordAssignedPropertyListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PublicPropertyListSerializer

    def get_queryset(self):
        return (
            Property.objects
            .filter(assigned_landlord=self.request.user)
            .prefetch_related("images")
            .order_by("-created_at")
        )


class LandlordComplaintListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LandlordComplaintSerializer

    def get_queryset(self):
        return (
            Complaint.objects
            .filter(property__assigned_landlord=self.request.user)
            .select_related("property")
            .order_by("-created_at")
        )


class LandlordCareTicketListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CareTicketSerializer

    def get_queryset(self):
        return (
            CareTicket.objects
            .filter(property__assigned_landlord=self.request.user, landlord_visible=True)
            .select_related("property", "tenancy", "application", "user", "assigned_to")
            .prefetch_related("events", "attachments")
            .order_by("-updated_at")
        )


class LandlordYOEMetricListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = YOEMetricSerializer

    def get_queryset(self):
        return (
            YOEMetric.objects
            .filter(landlord=self.request.user)
            .select_related("property", "landlord")
            .order_by("-net_yield")
        )


class LandlordRentLedgerListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LandlordRentLedgerSerializer

    def get_queryset(self):
        return (
            RentLedger.objects
            .filter(tenancy__property__assigned_landlord=self.request.user)
            .select_related("tenancy", "tenancy__property")
            .order_by("-due_date")
        )


class LandlordISRATierListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = []
        for tenancy in Tenancy.objects.filter(property__assigned_landlord=request.user, status=TenancyStatus.ACTIVE).select_related("property", "user"):
            score = getattr(tenancy.user, "isra_score", None)
            rows.append(
                {
                    "property": str(tenancy.property_id),
                    "property_title": tenancy.property.title,
                    "tier": score.risk_band if score else "PENDING",
                }
            )
        return Response(rows, status=status.HTTP_200_OK)


class LandlordEnquiryInsightsView(APIView):
    """
    Aggregated enquiry intelligence for landlords.
    Returns property-level match counts and contact enquiry signals
    without exposing any student identity.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Count
        from django.utils import timezone as tz

        properties = list(
            Property.objects.filter(assigned_landlord=request.user)
            .only("id", "title", "city", "locality", "is_featured")
        )
        if not properties:
            return Response({"properties": [], "weekly_total": 0, "weekly_by_day": []}, status=status.HTTP_200_OK)

        property_ids = [p.id for p in properties]

        # PropMatch hits per property (proxy for interest / enquiry signal)
        match_counts = dict(
            PropMatchResult.objects
            .filter(property_id__in=property_ids)
            .values("property_id")
            .annotate(c=Count("id"))
            .values_list("property_id", "c")
        )

        # Contact messages per property title (loose match — admin enters titles)
        # Use last 30 days for weekly signal approximation
        thirty_days_ago = tz.now() - tz.timedelta(days=30)
        contact_counts = {}
        for prop in properties:
            contact_counts[prop.id] = ContactMessage.objects.filter(
                created_at__gte=thirty_days_ago,
                message__icontains=prop.city,
            ).count()

        property_rows = []
        for prop in properties:
            hits = match_counts.get(prop.id, 0)
            contacts = contact_counts.get(prop.id, 0)
            total_signal = hits + contacts
            if total_signal >= 20:
                demand = "high"
            elif total_signal >= 8:
                demand = "medium"
            else:
                demand = "low"
            property_rows.append({
                "id": str(prop.id),
                "title": prop.title,
                "city": prop.city,
                "locality": prop.locality,
                "match_hits": hits,
                "contact_signals": contacts,
                "total_signal": total_signal,
                "demand": demand,
            })

        property_rows.sort(key=lambda r: r["total_signal"], reverse=True)

        # Weekly signal: PropMatch results created in the last 7 days grouped by day
        seven_days_ago = tz.now() - tz.timedelta(days=7)
        from django.db.models.functions import TruncDate
        daily_qs = (
            PropMatchResult.objects
            .filter(property_id__in=property_ids, generated_at__gte=seven_days_ago)
            .annotate(day=TruncDate("generated_at"))
            .values("day")
            .annotate(enquiries=Count("id"))
            .order_by("day")
        )
        weekly_by_day = [{"day": row["day"].strftime("%a"), "enquiries": row["enquiries"]} for row in daily_qs]
        weekly_total = sum(r["enquiries"] for r in weekly_by_day)

        return Response({
            "properties": property_rows,
            "weekly_total": weekly_total,
            "weekly_by_day": weekly_by_day,
        }, status=status.HTTP_200_OK)
