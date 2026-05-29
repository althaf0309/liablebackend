from django.db.models import Q
from django.utils import timezone

from rest_framework import generics, serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminOrStaff, IsAdminOrStaffReadOnlyOrAdminWrite
from accounts.models import UserRole

from .engines import calculate_isra_for_user, run_propmatch_for_user
from .models import (
    BlogPost,
    AuditLog,
    Complaint,
    ComplaintAttachment,
    HousingApplication,
    IntentForm,
    ISRAscore,
    PropMatchResult,
    Property,
    PropertyExpense,
    PropertyImage,
    PropertyVideo,
    RentLedger,
    TenancyHealthScore,
    TenancyRecord,
    Tenancy,
    YOEMetric,
    StudentDocument,
)
from .serializers import (
    ComplaintSerializer,
    AuditLogSerializer,
    ComplaintAttachmentSerializer,
    HousingApplicationSerializer,
    IntentFormSerializer,
    ISRAscoreSerializer,
    PropMatchResultSerializer,
    PropertyExpenseSerializer,
    PropertyImageSerializer,
    PropertyVideoSerializer,
    RentLedgerSerializer,
    TenancySerializer,
    TenancyHealthScoreSerializer,
    TenancyRecordSerializer,
    YOEMetricSerializer,
    StudentDocumentSerializer,
)
from .audit import write_audit_log
from .quantum_flow import advance_application_stage
from .yoe import calculate_yoe_for_property, refresh_yoe_metrics
from .tenancy_intelligence import refresh_tenancy_health_score, refresh_all_tenancy_health_scores, void_risk_rows


class AdminAuditMixin:
    audit_label = "admin_object"

    def perform_create(self, serializer):
        instance = serializer.save()
        write_audit_log(self.request, f"{self.audit_label}.create", instance)
        return instance

    def perform_update(self, serializer):
        instance = serializer.save()
        write_audit_log(self.request, f"{self.audit_label}.update", instance)
        return instance

    def perform_destroy(self, instance):
        write_audit_log(self.request, f"{self.audit_label}.delete", instance)
        instance.delete()


class AdminBlogWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogPost
        fields = [
            "id",
            "slug",
            "title",
            "excerpt",
            "content",
            "is_published",
            "published_at",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class AdminPropertyWriteSerializer(serializers.ModelSerializer):
    images = PropertyImageSerializer(many=True, read_only=True)
    videos = PropertyVideoSerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = [
            "id", "slug", "title", "description",
            "created_by", "assigned_landlord",
            "country", "state", "city", "locality",
            "address_line1", "address_line2", "postal_code",
            "latitude", "longitude", "map_pin_verified",
            "property_type", "room_type",
            "bedrooms", "bathrooms", "area_sqft",
            "currency", "rent_monthly", "deposit_amount", "maintenance_amount", "bills_included",
            "status", "available_from", "min_stay_months", "max_stay_months",
            "furnish_status",
            "has_wifi", "has_ac", "has_parking", "has_gym", "has_pool",
            "has_lift", "has_power_backup", "has_security", "has_cctv", "has_washing_machine",
            "smoking_allowed", "pets_allowed", "alcohol_allowed", "guests_allowed",
            "cover_image_url", "featured_video_url",
            "is_featured", "priority_rank", "isra_threshold", "internal_notes",
            "images", "videos",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AdminPropertyMediaWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = ["id", "property", "image_url", "alt_text", "caption", "is_cover", "sort_order", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        property_obj = attrs.get("property", getattr(self.instance, "property", None))
        if not property_obj:
            raise serializers.ValidationError("property is required.")
        return attrs


class AdminPropertyVideoWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyVideo
        fields = [
            "id", "property", "provider", "title", "video_url", "thumbnail_url",
            "is_featured", "sort_order", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        property_obj = attrs.get("property", getattr(self.instance, "property", None))
        if not property_obj:
            raise serializers.ValidationError("property is required.")
        return attrs


class AdminPropertyListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "property"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def get_queryset(self):
        qs = (
            Property.objects
            .prefetch_related("images", "videos")
            .order_by("-created_at")
        )
        q = (self.request.query_params.get("q") or "").strip()
        status_value = (self.request.query_params.get("status") or "").strip().upper()
        city = (self.request.query_params.get("city") or "").strip()

        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(slug__icontains=q) | Q(locality__icontains=q))
        if status_value:
            qs = qs.filter(status=status_value)
        if city:
            qs = qs.filter(city__icontains=city)
        return qs

    def get_serializer_class(self):
        return AdminPropertyWriteSerializer

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        write_audit_log(self.request, "property.create", instance)


class AdminPropertyDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "property"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    lookup_field = "id"

    def get_queryset(self):
        return Property.objects.prefetch_related("images", "videos")

    def get_serializer_class(self):
        return AdminPropertyWriteSerializer

    def perform_update(self, serializer):
        instance = serializer.save()
        if not instance.created_by_id:
            instance.created_by = self.request.user
            instance.save(update_fields=["created_by"])
        write_audit_log(self.request, "property.update", instance)


class AdminBlogListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "blog"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def get_queryset(self):
        qs = BlogPost.objects.order_by("-published_at", "-created_at")
        q = (self.request.query_params.get("q") or "").strip()
        is_published = (self.request.query_params.get("is_published") or "").strip().lower()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(slug__icontains=q) | Q(excerpt__icontains=q))
        if is_published in ["true", "false"]:
            qs = qs.filter(is_published=is_published == "true")
        return qs

    def get_serializer_class(self):
        return AdminBlogWriteSerializer


class AdminBlogDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "blog"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    queryset = BlogPost.objects.all()
    lookup_field = "id"

    def get_serializer_class(self):
        return AdminBlogWriteSerializer


class AdminPropertyImageListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "property_image"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = AdminPropertyMediaWriteSerializer

    def get_queryset(self):
        qs = PropertyImage.objects.select_related("property").order_by("property_id", "sort_order", "id")
        property_id = (self.request.query_params.get("property_id") or "").strip()
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs


class AdminPropertyImageDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "property_image"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = AdminPropertyMediaWriteSerializer
    queryset = PropertyImage.objects.select_related("property")
    lookup_field = "id"


class AdminPropertyVideoListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "property_video"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = AdminPropertyVideoWriteSerializer

    def get_queryset(self):
        qs = PropertyVideo.objects.select_related("property").order_by("property_id", "sort_order", "id")
        property_id = (self.request.query_params.get("property_id") or "").strip()
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs


class AdminPropertyVideoDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "property_video"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = AdminPropertyVideoWriteSerializer
    queryset = PropertyVideo.objects.select_related("property")
    lookup_field = "id"


class AdminIntentFormListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "intent_form"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = IntentFormSerializer

    def get_queryset(self):
        qs = IntentForm.objects.select_related("user").order_by("-created_at")
        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(user__email__icontains=q) | Q(user__full_name__icontains=q) | Q(city__icontains=q))
        return qs


class AdminIntentFormDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "intent_form"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = IntentFormSerializer
    queryset = IntentForm.objects.select_related("user")
    lookup_field = "id"


class AdminISRAscoreListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "isra_score"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaffReadOnlyOrAdminWrite]
    serializer_class = ISRAscoreSerializer

    def get_queryset(self):
        qs = ISRAscore.objects.select_related("user", "user__intent_form").order_by("-updated_at")
        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(user__email__icontains=q) | Q(user__full_name__icontains=q))
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        override = {
            "stability_score": serializer.validated_data.get("stability_score"),
            "financial_score": serializer.validated_data.get("financial_score"),
            "behavioural_score": serializer.validated_data.get("behavioural_score"),
            "notes": serializer.validated_data.get("notes", ""),
            "flags": serializer.validated_data.get("flags", []),
            "override_reason": serializer.validated_data.get("override_reason", ""),
        }
        score = calculate_isra_for_user(user, override=override)
        write_audit_log(request, "isra_score.create_override", score, {"user_id": str(user.id)})
        return Response(ISRAscoreSerializer(score).data, status=status.HTTP_201_CREATED)


class AdminISRAscoreDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "isra_score"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaffReadOnlyOrAdminWrite]
    serializer_class = ISRAscoreSerializer
    queryset = ISRAscore.objects.select_related("user", "user__intent_form")
    lookup_field = "id"

    def perform_update(self, serializer):
        instance = serializer.save()
        calculate_isra_for_user(
            instance.user,
            override={
                "stability_score": instance.stability_score,
                "financial_score": instance.financial_score,
                "behavioural_score": instance.behavioural_score,
                "notes": instance.notes,
                "flags": instance.flags,
                "override_reason": instance.override_reason,
            },
        )
        write_audit_log(self.request, "isra_score.update_override", instance, {"user_id": str(instance.user_id)})


class AdminRunISRAView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def post(self, request, user_id):
        from accounts.models import User

        user = User.objects.get(id=user_id)
        score = calculate_isra_for_user(user)
        write_audit_log(request, "isra_score.run", score, {"user_id": str(user.id)})
        return Response(ISRAscoreSerializer(score).data, status=status.HTTP_200_OK)


class AdminRunPropMatchView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def post(self, request, user_id):
        from accounts.models import User

        user = User.objects.get(id=user_id)
        if not hasattr(user, "isra_score"):
            calculate_isra_for_user(user)
        results = run_propmatch_for_user(user)
        write_audit_log(request, "propmatch.run", user, {"user_id": str(user.id), "result_count": len(results)})
        return Response(PropMatchResultSerializer(results, many=True).data, status=status.HTTP_200_OK)


class AdminPropMatchResultListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = PropMatchResultSerializer

    def get_queryset(self):
        qs = PropMatchResult.objects.select_related("user", "property").prefetch_related("property__images")
        user_id = (self.request.query_params.get("user_id") or "").strip()
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs.order_by("user_id", "rank")


class AdminHousingApplicationListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "housing_application"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = HousingApplicationSerializer

    def get_queryset(self):
        qs = HousingApplication.objects.select_related("user", "property", "prop_match").order_by("-updated_at")
        q = (self.request.query_params.get("q") or "").strip()
        stage = (self.request.query_params.get("stage") or "").strip().upper()
        status_value = (self.request.query_params.get("status") or "").strip().upper()
        if q:
            qs = qs.filter(Q(user__email__icontains=q) | Q(user__full_name__icontains=q) | Q(property__title__icontains=q))
        if stage:
            qs = qs.filter(stage=stage)
        if status_value:
            qs = qs.filter(status=status_value)
        return qs

    def perform_create(self, serializer):
        application = serializer.save()
        if not application.next_action:
            advance_application_stage(application, application.stage, actor=self.request.user)
        write_audit_log(self.request, "housing_application.create", application, {"stage": application.stage})


class AdminHousingApplicationDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "housing_application"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = HousingApplicationSerializer
    queryset = HousingApplication.objects.select_related("user", "property", "prop_match")
    lookup_field = "id"

    def perform_update(self, serializer):
        previous_stage = self.get_object().stage
        application = serializer.save()
        if application.stage != previous_stage:
            advance_application_stage(application, application.stage, actor=self.request.user, previous_stage=previous_stage)
        write_audit_log(self.request, "housing_application.update", application, {"stage": application.stage})


class AdminTenancyListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "tenancy"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = TenancySerializer
    queryset = Tenancy.objects.select_related("user", "property").order_by("-created_at")

    def perform_create(self, serializer):
        tenancy = serializer.save()
        refresh_tenancy_health_score(tenancy)
        write_audit_log(self.request, "tenancy.create", tenancy)


class AdminTenancyDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "tenancy"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = TenancySerializer
    queryset = Tenancy.objects.select_related("user", "property")
    lookup_field = "id"

    def perform_update(self, serializer):
        tenancy = serializer.save()
        refresh_tenancy_health_score(tenancy)
        write_audit_log(self.request, "tenancy.update", tenancy)


class AdminComplaintListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "complaint"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = ComplaintSerializer
    queryset = Complaint.objects.select_related("user", "property").order_by("-created_at")

    def perform_create(self, serializer):
        complaint = serializer.save()
        tenancy = Tenancy.objects.filter(user=complaint.user, property=complaint.property).order_by("-start_date").first()
        if tenancy:
            refresh_tenancy_health_score(tenancy)
        write_audit_log(self.request, "complaint.create", complaint)


class AdminComplaintDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "complaint"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = ComplaintSerializer
    queryset = Complaint.objects.select_related("user", "property")
    lookup_field = "id"

    def perform_update(self, serializer):
        complaint = serializer.save()
        tenancy = Tenancy.objects.filter(user=complaint.user, property=complaint.property).order_by("-start_date").first()
        if tenancy:
            refresh_tenancy_health_score(tenancy)
        write_audit_log(self.request, "complaint.update", complaint)


class AdminTenancyHealthListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = TenancyHealthScoreSerializer

    def get_queryset(self):
        refresh_all_tenancy_health_scores()
        return (
            TenancyHealthScore.objects
            .select_related("tenancy", "tenancy__user", "tenancy__property")
            .prefetch_related("tenancy__health_events")
            .order_by("score")
        )


class AdminTenancyRecordListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = TenancyRecordSerializer
    queryset = TenancyRecord.objects.select_related("user", "tenancy", "property").order_by("-issued_at")


class AdminVoidRiskListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        return Response(void_risk_rows(), status=status.HTTP_200_OK)


class AdminStudentDocumentListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = StudentDocumentSerializer

    def get_queryset(self):
        qs = StudentDocument.objects.select_related("user").order_by("-uploaded_at")
        user_id = (self.request.query_params.get("user_id") or "").strip()
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs


class AdminStudentDocumentDetailView(AdminAuditMixin, generics.RetrieveUpdateAPIView):
    audit_label = "student_document"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = StudentDocumentSerializer
    queryset = StudentDocument.objects.select_related("user")
    lookup_field = "id"

    def perform_update(self, serializer):
        instance = serializer.save()
        if instance.verification_status != "PENDING" and not instance.reviewed_at:
            instance.reviewed_at = timezone.now()
        if instance.verification_status != "PENDING":
            instance.reviewed_by = self.request.user
        instance.save(update_fields=["reviewed_at", "reviewed_by"])
        write_audit_log(
            self.request,
            "student_document.review",
            instance,
            {
                "status": instance.verification_status,
                "reviewed_by": str(self.request.user.id),
            },
        )


class AdminComplaintAttachmentListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = ComplaintAttachmentSerializer

    def get_queryset(self):
        qs = ComplaintAttachment.objects.select_related("complaint", "complaint__property").order_by("-uploaded_at")
        complaint_id = (self.request.query_params.get("complaint_id") or "").strip()
        if complaint_id:
            qs = qs.filter(complaint_id=complaint_id)
        return qs


class AdminPropertyExpenseListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "property_expense"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = PropertyExpenseSerializer
    queryset = PropertyExpense.objects.select_related("property", "landlord").order_by("-incurred_on")


class AdminPropertyExpenseDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "property_expense"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = PropertyExpenseSerializer
    queryset = PropertyExpense.objects.select_related("property", "landlord")
    lookup_field = "id"


class AdminRentLedgerListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "rent_ledger"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = RentLedgerSerializer
    queryset = RentLedger.objects.select_related("tenancy", "tenancy__user", "tenancy__property").order_by("-due_date")

    def perform_create(self, serializer):
        row = serializer.save()
        refresh_tenancy_health_score(row.tenancy)
        write_audit_log(self.request, "rent_ledger.create", row)


class AdminRentLedgerDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "rent_ledger"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = RentLedgerSerializer
    queryset = RentLedger.objects.select_related("tenancy", "tenancy__user", "tenancy__property")
    lookup_field = "id"

    def perform_update(self, serializer):
        row = serializer.save()
        refresh_tenancy_health_score(row.tenancy)
        write_audit_log(self.request, "rent_ledger.update", row)


class AdminYOEMetricListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = YOEMetricSerializer

    def get_queryset(self):
        qs = YOEMetric.objects.select_related("property", "landlord").order_by("-net_yield")
        landlord_id = (self.request.query_params.get("landlord_id") or "").strip()
        if landlord_id:
            qs = qs.filter(landlord_id=landlord_id)
        return qs


class AdminYOEMetricDetailView(AdminAuditMixin, generics.RetrieveUpdateAPIView):
    audit_label = "yoe_metric"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = YOEMetricSerializer
    queryset = YOEMetric.objects.select_related("property", "landlord")
    lookup_field = "id"

    def perform_update(self, serializer):
        instance = serializer.save()
        calculate_yoe_for_property(instance.property, property_value=instance.property_value)
        write_audit_log(self.request, "yoe_metric.update", instance)


class AdminRunYOEView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def post(self, request):
        metrics = refresh_yoe_metrics()
        write_audit_log(request, "yoe.run", None, {"result_count": len(metrics)})
        return Response(YOEMetricSerializer(metrics, many=True).data, status=status.HTTP_200_OK)


class AdminAuditLogListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        qs = AuditLog.objects.select_related("actor").order_by("-created_at")
        action = (self.request.query_params.get("action") or "").strip()
        actor_id = (self.request.query_params.get("actor_id") or "").strip()
        target_type = (self.request.query_params.get("target_type") or "").strip()
        target_id = (self.request.query_params.get("target_id") or "").strip()

        if action:
            qs = qs.filter(action__icontains=action)
        if actor_id:
            qs = qs.filter(actor_id=actor_id)
        if target_type:
            qs = qs.filter(target_type__iexact=target_type)
        if target_id:
            qs = qs.filter(target_id=target_id)
        return qs[:250]
