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
    AssistReminder,
    AssistReminderStatus,
    BlogPost,
    CareTicket,
    CareTicketAttachment,
    CareTicketStatus,
    AuditLog,
    Complaint,
    ComplaintAttachment,
    ApplicationEntryStatus,
    HousingApplication,
    ApplicationTimelineEvent,
    IntentForm,
    ISRAscore,
    PropMatchResult,
    PropMatchScoreHistory,
    Property,
    PropertyExpense,
    PropertyImage,
    PropertyVideo,
    RentLedger,
    TenancyHealthScore,
    TenancyRecord,
    Tenancy,
    TenancyStatus,
    VerificationState,
    YOEMetric,
    StudentDocument,
    SupportRequest,
    SupportRequestAttachment,
    SupportRequestStatus,
)
from .serializers import (
    AssistReminderSerializer,
    ComplaintSerializer,
    CareTicketSerializer,
    CareTicketAttachmentSerializer,
    SupportRequestSerializer,
    SupportRequestAttachmentSerializer,
    AuditLogSerializer,
    ComplaintAttachmentSerializer,
    HousingApplicationSerializer,
    IntentFormSerializer,
    ISRAscoreSerializer,
    PropMatchResultSerializer,
    PropMatchScoreHistorySerializer,
    PropertyExpenseSerializer,
    PropertyImageSerializer,
    PropertyVideoSerializer,
    RentLedgerSerializer,
    ApplicationTimelineEventSerializer,
    NotificationSerializer,
    TenancySerializer,
    TenancyHealthScoreSerializer,
    TenancyRecordSerializer,
    YOEMetricSerializer,
    StudentDocumentSerializer,
)
from .audit import write_audit_log
from .assist import create_assist_log, process_due_assist_reminders, update_assist_reminder_status
from .care import create_care_event, update_care_ticket_status
from .document_verification import refresh_application_verification_state, refresh_user_open_applications
from .monitoring import build_production_monitoring_status
from .quantum_flow import advance_application_stage
from .reporting import build_production_report
from .support import create_support_event, update_support_request_status
from .support_intelligence import build_support_intelligence
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


class AdminPropMatchScoreHistoryListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = PropMatchScoreHistorySerializer

    def get_queryset(self):
        qs = PropMatchScoreHistory.objects.select_related("user", "property").prefetch_related("property__images")
        user_id = (self.request.query_params.get("user_id") or "").strip()
        property_id = (self.request.query_params.get("property_id") or "").strip()
        run_id = (self.request.query_params.get("run_id") or "").strip()
        eligible = (self.request.query_params.get("eligible") or "").strip().lower()
        if user_id:
            qs = qs.filter(user_id=user_id)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if run_id:
            qs = qs.filter(run_id=run_id)
        if eligible in ["true", "false"]:
            qs = qs.filter(eligible=eligible == "true")
        return qs.order_by("-generated_at", "rank", "-confidence_score")


class AdminHousingApplicationListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "housing_application"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = HousingApplicationSerializer

    def get_queryset(self):
        qs = HousingApplication.objects.select_related("user", "property", "prop_match").order_by("-updated_at")
        q = (self.request.query_params.get("q") or "").strip()
        stage = (self.request.query_params.get("stage") or "").strip().upper()
        entry_status = (self.request.query_params.get("entry_status") or "").strip().upper()
        status_value = (self.request.query_params.get("status") or "").strip().upper()
        if q:
            qs = qs.filter(Q(user__email__icontains=q) | Q(user__full_name__icontains=q) | Q(property__title__icontains=q))
        if stage:
            qs = qs.filter(stage=stage)
        if entry_status:
            qs = qs.filter(entry_status=entry_status)
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
        previous = self.get_object()
        previous_stage = previous.stage
        previous_entry_status = previous.entry_status
        application = serializer.save()
        if (
            application.entry_status != previous_entry_status
            and application.entry_status in [ApplicationEntryStatus.IN_REVIEW, ApplicationEntryStatus.READY]
            and not application.entry_reviewed_at
        ):
            application.entry_reviewed_at = timezone.now()
            application.save(update_fields=["entry_reviewed_at", "updated_at"])
        if application.stage != previous_stage:
            advance_application_stage(application, application.stage, actor=self.request.user, previous_stage=previous_stage)
        write_audit_log(
            self.request,
            "housing_application.update",
            application,
            {
                "stage": application.stage,
                "entry_status": application.entry_status,
                "previous_entry_status": previous_entry_status,
            },
        )


class AdminApplicationTimelineListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = ApplicationTimelineEventSerializer

    def get_queryset(self):
        qs = ApplicationTimelineEvent.objects.select_related("application", "actor", "application__user", "application__property")
        application_id = (self.request.query_params.get("application_id") or "").strip()
        user_id = (self.request.query_params.get("user_id") or "").strip()
        event_type = (self.request.query_params.get("event_type") or "").strip().upper()
        if application_id:
            qs = qs.filter(application_id=application_id)
        if user_id:
            qs = qs.filter(application__user_id=user_id)
        if event_type:
            qs = qs.filter(event_type=event_type)
        return qs.order_by("-created_at")


class AdminAssistReminderListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "assist_reminder"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaffReadOnlyOrAdminWrite]
    serializer_class = AssistReminderSerializer

    def get_queryset(self):
        qs = (
            AssistReminder.objects
            .select_related("user", "application", "tenancy", "care_ticket", "support_request", "created_by", "assigned_to")
            .prefetch_related("automation_logs")
        )
        user_id = (self.request.query_params.get("user_id") or "").strip()
        status_value = (self.request.query_params.get("status") or "").strip().upper()
        reminder_type = (self.request.query_params.get("reminder_type") or "").strip().upper()
        if user_id:
            qs = qs.filter(user_id=user_id)
        if status_value:
            qs = qs.filter(status=status_value)
        if reminder_type:
            qs = qs.filter(reminder_type=reminder_type)
        return qs.order_by("due_at", "-created_at")

    def perform_create(self, serializer):
        reminder = serializer.save(created_by=self.request.user)
        create_assist_log(reminder, "CREATED", "Assist reminder created.", actor=self.request.user)
        write_audit_log(
            self.request,
            "assist_reminder.create",
            reminder,
            {
                "status": reminder.status,
                "reminder_type": reminder.reminder_type,
                "due_at": reminder.due_at.isoformat(),
            },
        )


class AdminAssistReminderDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "assist_reminder"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaffReadOnlyOrAdminWrite]
    serializer_class = AssistReminderSerializer
    queryset = AssistReminder.objects.select_related("user", "application", "tenancy", "care_ticket", "support_request", "created_by", "assigned_to").prefetch_related("automation_logs")
    lookup_field = "id"

    def perform_update(self, serializer):
        previous = self.get_object()
        previous_status = previous.status
        reminder = serializer.save()
        if reminder.status != previous_status:
            new_status = reminder.status
            reminder.status = previous_status
            update_assist_reminder_status(
                reminder,
                new_status,
                actor=self.request.user,
                internal_notes=reminder.internal_notes,
            )
        write_audit_log(
            self.request,
            "assist_reminder.update",
            reminder,
            {
                "previous_status": previous_status,
                "status": reminder.status,
                "reminder_type": reminder.reminder_type,
            },
        )


class AdminRunAssistDueRemindersView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaffReadOnlyOrAdminWrite]

    def post(self, request):
        processed = process_due_assist_reminders(actor=request.user)
        write_audit_log(
            request,
            "assist_reminder.process_due",
            request.user,
            {"processed_count": len(processed)},
        )
        return Response(
            {
                "processed_count": len(processed),
                "reminders": AssistReminderSerializer(processed, many=True, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )


def _auto_create_tenancy_record(tenancy):
    """Create a portable TenancyRecord when a tenancy transitions to ENDED."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        if hasattr(tenancy, "portable_record"):
            return  # already exists
        ths = getattr(tenancy, "health_score", None)
        ths_score = ths.score if ths else 0
        badge = "Good Standing" if ths_score >= 70 else "Completed"
        outcome = "Tenancy completed successfully." if ths_score >= 70 else "Tenancy ended."
        import uuid as _uuid
        cert_code = f"TR-{str(_uuid.uuid4()).upper()[:12]}"
        TenancyRecord.objects.create(
            user=tenancy.user,
            tenancy=tenancy,
            property=tenancy.property,
            badge_label=badge,
            outcome=outcome,
            ths_score_snapshot=ths_score,
            certificate_code=cert_code,
        )
    except Exception:
        logger.exception("Failed to auto-create TenancyRecord for tenancy %s", tenancy.id)


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
        previous_status = serializer.instance.status
        tenancy = serializer.save()
        refresh_tenancy_health_score(tenancy)
        write_audit_log(self.request, "tenancy.update", tenancy)
        if previous_status != TenancyStatus.ENDED and tenancy.status == TenancyStatus.ENDED:
            _auto_create_tenancy_record(tenancy)


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


class AdminCareTicketListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "care_ticket"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaffReadOnlyOrAdminWrite]
    serializer_class = CareTicketSerializer

    def get_queryset(self):
        qs = CareTicket.objects.select_related("user", "property", "tenancy", "application", "assigned_to").prefetch_related("events", "attachments")
        user_id = (self.request.query_params.get("user_id") or "").strip()
        property_id = (self.request.query_params.get("property_id") or "").strip()
        status_value = (self.request.query_params.get("status") or "").strip().upper()
        category = (self.request.query_params.get("category") or "").strip().upper()
        if user_id:
            qs = qs.filter(user_id=user_id)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if status_value:
            qs = qs.filter(status=status_value)
        if category:
            qs = qs.filter(category=category)
        return qs.order_by("-updated_at")

    def perform_create(self, serializer):
        ticket = serializer.save()
        if not ticket.status:
            ticket.status = CareTicketStatus.OPEN
            ticket.save(update_fields=["status", "updated_at"])
        create_care_event(ticket, actor=self.request.user)
        write_audit_log(self.request, "care_ticket.create", ticket, {"status": ticket.status, "category": ticket.category})


class AdminCareTicketDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "care_ticket"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaffReadOnlyOrAdminWrite]
    serializer_class = CareTicketSerializer
    queryset = CareTicket.objects.select_related("user", "property", "tenancy", "application", "assigned_to").prefetch_related("events", "attachments")
    lookup_field = "id"

    def perform_update(self, serializer):
        previous = self.get_object()
        previous_status = previous.status
        ticket = serializer.save()
        if ticket.status != previous_status:
            new_status = ticket.status
            ticket.status = previous_status
            update_care_ticket_status(
                ticket,
                new_status,
                actor=self.request.user,
                student_safe_summary=ticket.student_safe_summary,
                internal_notes=ticket.internal_notes,
                assigned_to=ticket.assigned_to,
            )
        write_audit_log(
            self.request,
            "care_ticket.update",
            ticket,
            {
                "previous_status": previous_status,
                "status": ticket.status,
                "category": ticket.category,
                "priority": ticket.priority,
            },
        )


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
        qs = StudentDocument.objects.select_related("user", "application").order_by("-uploaded_at")
        user_id = (self.request.query_params.get("user_id") or "").strip()
        application_id = (self.request.query_params.get("application_id") or "").strip()
        verification_status = (self.request.query_params.get("verification_status") or "").strip().upper()
        document_type = (self.request.query_params.get("document_type") or "").strip().upper()
        if user_id:
            qs = qs.filter(user_id=user_id)
        if application_id:
            qs = qs.filter(application_id=application_id)
        if verification_status:
            qs = qs.filter(verification_status=verification_status)
        if document_type:
            qs = qs.filter(document_type=document_type)
        return qs


class AdminStudentDocumentDetailView(AdminAuditMixin, generics.RetrieveUpdateAPIView):
    audit_label = "student_document"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = StudentDocumentSerializer
    queryset = StudentDocument.objects.select_related("user", "application")
    lookup_field = "id"

    def perform_update(self, serializer):
        previous_status = self.get_object().verification_status
        instance = serializer.save()
        if instance.verification_status != "PENDING" and not instance.reviewed_at:
            instance.reviewed_at = timezone.now()
        if instance.verification_status != "PENDING":
            instance.reviewed_by = self.request.user
        update_fields = ["reviewed_at", "reviewed_by"]
        if instance.verification_status == VerificationState.RESUBMISSION_REQUIRED and not instance.resubmission_requested_at:
            instance.resubmission_requested_at = timezone.now()
            update_fields.append("resubmission_requested_at")
        instance.save(update_fields=update_fields)
        if instance.application_id:
            refresh_application_verification_state(instance.application)
        else:
            refresh_user_open_applications(instance.user)
        write_audit_log(
            self.request,
            "student_document.review",
            instance,
            {
                "status": instance.verification_status,
                "previous_status": previous_status,
                "application_id": str(instance.application_id) if instance.application_id else None,
                "document_type": instance.document_type,
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


class AdminCareTicketAttachmentListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = CareTicketAttachmentSerializer

    def get_queryset(self):
        qs = CareTicketAttachment.objects.select_related("ticket", "ticket__property", "uploaded_by").order_by("-uploaded_at")
        ticket_id = (self.request.query_params.get("ticket_id") or "").strip()
        if ticket_id:
            qs = qs.filter(ticket_id=ticket_id)
        return qs


class AdminSupportRequestListCreateView(AdminAuditMixin, generics.ListCreateAPIView):
    audit_label = "support_request"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaffReadOnlyOrAdminWrite]
    serializer_class = SupportRequestSerializer

    def get_queryset(self):
        qs = SupportRequest.objects.select_related("user", "application", "assigned_to").prefetch_related("events", "attachments")
        user_id = (self.request.query_params.get("user_id") or "").strip()
        application_id = (self.request.query_params.get("application_id") or "").strip()
        status_value = (self.request.query_params.get("status") or "").strip().upper()
        category = (self.request.query_params.get("category") or "").strip().upper()
        if user_id:
            qs = qs.filter(user_id=user_id)
        if application_id:
            qs = qs.filter(application_id=application_id)
        if status_value:
            qs = qs.filter(status=status_value)
        if category:
            qs = qs.filter(category=category)
        return qs.order_by("-updated_at")

    def perform_create(self, serializer):
        support_request = serializer.save()
        if not support_request.status:
            support_request.status = SupportRequestStatus.OPEN
            support_request.save(update_fields=["status", "updated_at"])
        create_support_event(support_request, actor=self.request.user)
        write_audit_log(
            self.request,
            "support_request.create",
            support_request,
            {"status": support_request.status, "category": support_request.category},
        )


class AdminSupportRequestDetailView(AdminAuditMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_label = "support_request"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaffReadOnlyOrAdminWrite]
    serializer_class = SupportRequestSerializer
    queryset = SupportRequest.objects.select_related("user", "application", "assigned_to").prefetch_related("events", "attachments")
    lookup_field = "id"

    def perform_update(self, serializer):
        previous = self.get_object()
        previous_status = previous.status
        support_request = serializer.save()
        if support_request.status != previous_status:
            new_status = support_request.status
            support_request.status = previous_status
            update_support_request_status(
                support_request,
                new_status,
                actor=self.request.user,
                student_safe_summary=support_request.student_safe_summary,
                internal_notes=support_request.internal_notes,
                assigned_to=support_request.assigned_to,
            )
        write_audit_log(
            self.request,
            "support_request.update",
            support_request,
            {
                "previous_status": previous_status,
                "status": support_request.status,
                "category": support_request.category,
                "priority": support_request.priority,
            },
        )


class AdminSupportRequestAttachmentListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = SupportRequestAttachmentSerializer

    def get_queryset(self):
        qs = SupportRequestAttachment.objects.select_related("support_request", "support_request__user", "uploaded_by").order_by("-uploaded_at")
        support_request_id = (self.request.query_params.get("support_request_id") or "").strip()
        if support_request_id:
            qs = qs.filter(support_request_id=support_request_id)
        return qs


class AdminSupportIntelligenceView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def post(self, request):
        query = str(request.data.get("query") or "").strip()
        support_request_id = str(request.data.get("support_request_id") or "").strip()
        if not query and not support_request_id:
            return Response({"detail": "query or support_request_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            build_support_intelligence(query or "Support request guidance", support_request_id=support_request_id),
            status=status.HTTP_200_OK,
        )


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


class AdminProductionReportView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        return Response(build_production_report(), status=status.HTTP_200_OK)


class AdminProductionMonitoringView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        return Response(build_production_monitoring_status(), status=status.HTTP_200_OK)


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
