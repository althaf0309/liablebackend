from django.db import connection
from django.db.models import Q
from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from rest_framework.generics import CreateAPIView, ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .engines import calculate_isra_for_user, run_propmatch_for_user
from .models import *
from .serializers import *
from .audit import write_audit_log
from .quantum_flow import create_application_for_user
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
        )
        write_audit_log(request, "housing_application.create", application, {"stage": application.stage})
        return Response(HousingApplicationSerializer(application).data, status=status.HTTP_201_CREATED)


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

        document = StudentDocument.objects.create(
            user=request.user,
            document_type=request.data.get("document_type") or StudentDocumentType.OTHER,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            content_type=uploaded_file.content_type or "",
            file_size=uploaded_file.size,
        )
        write_audit_log(
            request,
            "student_document.upload",
            document,
            {
                "document_type": document.document_type,
                "content_type": document.content_type,
                "file_size": document.file_size,
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
