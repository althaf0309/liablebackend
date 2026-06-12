"""
Operational API views for Steps 5-9:
  BookingHold, TenancyContractRecord, WorkflowTask, LifecycleRecord, AssistSuggestion
"""
import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from rest_framework import generics, serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminOrStaff
from .models import (
    BookingHold,
    BookingHoldStatus,
    TenancyContractRecord,
    ContractFieldStatus,
    WorkflowTask,
    WorkflowTaskStatus,
    WorkflowTaskType,
    WorkflowTaskPriority,
    LifecycleRecord,
    LifecycleEvent,
    LifecycleStage,
    AssistSuggestion,
    SuggestionStatus,
    AuditLog,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# STEP 5 — BOOKING HOLD
# ═══════════════════════════════════════════════════════════════════

class BookingHoldSerializer(serializers.ModelSerializer):
    student_email = serializers.CharField(source="student.email", read_only=True)
    property_title = serializers.CharField(source="property.title", read_only=True)
    reviewed_by_email = serializers.CharField(source="reviewed_by.email", read_only=True, default=None)

    class Meta:
        model = BookingHold
        fields = [
            "id", "student", "student_email", "property", "property_title",
            "application", "status", "student_notes", "admin_notes",
            "reviewed_by", "reviewed_by_email", "reviewed_at",
            "expires_at", "requested_at", "updated_at",
        ]
        read_only_fields = [
            "id", "student_email", "property_title", "reviewed_by_email",
            "reviewed_at", "requested_at", "updated_at",
        ]


class StudentBookingHoldCreateView(APIView):
    """Student requests a hold on a property."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        property_id = request.data.get("property")
        application_id = request.data.get("application")
        notes = request.data.get("student_notes", "").strip()

        if not property_id:
            return Response({"detail": "property is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Prevent duplicate active holds
        existing = BookingHold.objects.filter(
            student=request.user,
            property_id=property_id,
            status__in=[
                BookingHoldStatus.REQUESTED,
                BookingHoldStatus.ADMIN_REVIEW,
                BookingHoldStatus.APPROVED,
                BookingHoldStatus.PROPERTY_RESERVED,
            ],
        ).first()
        if existing:
            return Response(
                {"detail": "You already have an active hold on this property."},
                status=status.HTTP_409_CONFLICT,
            )

        hold = BookingHold.objects.create(
            student=request.user,
            property_id=property_id,
            application_id=application_id or None,
            student_notes=notes,
            status=BookingHoldStatus.REQUESTED,
        )
        return Response(BookingHoldSerializer(hold).data, status=status.HTTP_201_CREATED)

    def get(self, request):
        holds = BookingHold.objects.filter(student=request.user).order_by("-requested_at")
        return Response(BookingHoldSerializer(holds, many=True).data)


class AdminBookingHoldListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = BookingHoldSerializer

    def get_queryset(self):
        qs = BookingHold.objects.select_related(
            "student", "property", "application", "reviewed_by"
        ).order_by("-requested_at")
        s = self.request.query_params.get("status", "").strip().upper()
        if s:
            qs = qs.filter(status=s)
        return qs


class AdminBookingHoldActionView(APIView):
    """Admin approves or rejects a booking hold."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    @transaction.atomic
    def post(self, request, id, action):
        try:
            hold = BookingHold.objects.select_for_update().get(pk=id)
        except BookingHold.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if hold.status not in [BookingHoldStatus.REQUESTED, BookingHoldStatus.ADMIN_REVIEW]:
            return Response(
                {"detail": f"Hold is already {hold.status}."},
                status=status.HTTP_409_CONFLICT,
            )

        admin_notes = request.data.get("admin_notes", "").strip()
        hold.reviewed_by = request.user
        hold.reviewed_at = timezone.now()
        hold.admin_notes = admin_notes

        if action == "approve":
            hold_days = int(request.data.get("hold_days", 7))
            hold.status = BookingHoldStatus.APPROVED
            hold.expires_at = timezone.now() + timezone.timedelta(days=hold_days)
        elif action == "reject":
            hold.status = BookingHoldStatus.REJECTED
        else:
            return Response({"detail": "action must be approve or reject."}, status=status.HTTP_400_BAD_REQUEST)

        hold.save()
        AuditLog.objects.create(
            actor=request.user,
            action=f"BOOKING_HOLD_{action.upper()}",
            target_type="BookingHold",
            target_id=str(hold.id),
        )
        return Response(BookingHoldSerializer(hold).data)


# ═══════════════════════════════════════════════════════════════════
# STEP 6 — TENANCY CONTRACT RECORD
# ═══════════════════════════════════════════════════════════════════

class TenancyContractRecordSerializer(serializers.ModelSerializer):
    updated_by_email = serializers.CharField(source="updated_by.email", read_only=True, default=None)

    class Meta:
        model = TenancyContractRecord
        fields = [
            "id", "tenancy",
            "agreement_status", "right_to_rent_status",
            "inventory_status", "deposit_status",
            "notes", "updated_by", "updated_by_email", "updated_at", "created_at",
        ]
        read_only_fields = ["id", "tenancy", "updated_by_email", "updated_at", "created_at"]


class TenancyContractRecordView(APIView):
    """GET or PUT the contract checklist for a tenancy."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def _get_or_create(self, tenancy_id):
        record, _ = TenancyContractRecord.objects.get_or_create(tenancy_id=tenancy_id)
        return record

    def get(self, request, tenancy_id):
        record = self._get_or_create(tenancy_id)
        return Response(TenancyContractRecordSerializer(record).data)

    def put(self, request, tenancy_id):
        record = self._get_or_create(tenancy_id)
        writable_fields = [
            "agreement_status", "right_to_rent_status",
            "inventory_status", "deposit_status", "notes",
        ]
        for field in writable_fields:
            if field in request.data:
                setattr(record, field, request.data[field])
        record.updated_by = request.user
        record.save()
        AuditLog.objects.create(
            actor=request.user,
            action="CONTRACT_RECORD_UPDATE",
            target_type="TenancyContractRecord",
            target_id=str(record.id),
            metadata={f: getattr(record, f) for f in writable_fields},
        )
        return Response(TenancyContractRecordSerializer(record).data)


# ═══════════════════════════════════════════════════════════════════
# STEP 7 — WORKFLOW TASK QUEUE
# ═══════════════════════════════════════════════════════════════════

class WorkflowTaskSerializer(serializers.ModelSerializer):
    assigned_to_email = serializers.CharField(source="assigned_to.email", read_only=True, default=None)
    created_by_email = serializers.CharField(source="created_by.email", read_only=True, default=None)

    class Meta:
        model = WorkflowTask
        fields = [
            "id", "task_type", "title", "description",
            "status", "priority",
            "assigned_to", "assigned_to_email",
            "created_by", "created_by_email",
            "application", "tenancy",
            "due_date", "blocked_reason",
            "completed_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by_email", "assigned_to_email", "completed_at", "created_at", "updated_at"]


class WorkflowTaskListCreateView(generics.ListCreateAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = WorkflowTaskSerializer

    def get_queryset(self):
        qs = WorkflowTask.objects.select_related(
            "assigned_to", "created_by", "application", "tenancy"
        ).order_by("-created_at")

        s = self.request.query_params.get("status", "").strip().upper()
        p = self.request.query_params.get("priority", "").strip().upper()
        assignee = self.request.query_params.get("assigned_to", "").strip()
        overdue = self.request.query_params.get("overdue", "").strip()

        if s:
            qs = qs.filter(status=s)
        if p:
            qs = qs.filter(priority=p)
        if assignee:
            qs = qs.filter(assigned_to_id=assignee)
        if overdue == "true":
            qs = qs.filter(due_date__lt=timezone.now(), status__in=[WorkflowTaskStatus.OPEN, WorkflowTaskStatus.IN_PROGRESS])
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class WorkflowTaskDetailView(generics.RetrieveUpdateAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = WorkflowTaskSerializer
    queryset = WorkflowTask.objects.select_related("assigned_to", "created_by")
    lookup_field = "id"


class WorkflowTaskCompleteView(APIView):
    """Mark a workflow task as done."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def post(self, request, id):
        try:
            task = WorkflowTask.objects.get(pk=id)
        except WorkflowTask.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if task.status == WorkflowTaskStatus.DONE:
            return Response({"detail": "Task already done."}, status=status.HTTP_409_CONFLICT)

        task.status = WorkflowTaskStatus.DONE
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at", "updated_at"])
        return Response(WorkflowTaskSerializer(task).data)


# ═══════════════════════════════════════════════════════════════════
# STEP 8 — LIFECYCLE RECORD
# ═══════════════════════════════════════════════════════════════════

class LifecycleEventSerializer(serializers.ModelSerializer):
    created_by_email = serializers.CharField(source="created_by.email", read_only=True, default=None)

    class Meta:
        model = LifecycleEvent
        fields = ["id", "from_stage", "to_stage", "description", "created_by_email", "created_at"]


class LifecycleRecordSerializer(serializers.ModelSerializer):
    student_email = serializers.CharField(source="student.email", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    events = LifecycleEventSerializer(many=True, read_only=True)

    class Meta:
        model = LifecycleRecord
        fields = [
            "id", "student", "student_email", "student_name",
            "current_stage", "application", "tenancy", "agency_referral",
            "notes", "stage_entered_at", "last_updated_at", "created_at",
            "events",
        ]
        read_only_fields = ["id", "student_email", "student_name", "stage_entered_at", "last_updated_at", "created_at"]


class AdminLifecycleRecordListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = LifecycleRecordSerializer

    def get_queryset(self):
        qs = LifecycleRecord.objects.select_related(
            "student", "application", "tenancy"
        ).prefetch_related("events").order_by("-created_at")

        stage = self.request.query_params.get("stage", "").strip().upper()
        q = self.request.query_params.get("q", "").strip()
        if stage:
            qs = qs.filter(current_stage=stage)
        if q:
            qs = qs.filter(Q(student__email__icontains=q) | Q(student__full_name__icontains=q))
        return qs


class AdminLifecycleRecordDetailView(generics.RetrieveAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = LifecycleRecordSerializer
    queryset = LifecycleRecord.objects.select_related(
        "student", "application", "tenancy"
    ).prefetch_related("events")
    lookup_field = "id"


class AdminLifecycleAdvanceView(APIView):
    """Admin advances a student to the next lifecycle stage."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    STAGE_ORDER = [
        LifecycleStage.INQUIRY, LifecycleStage.VERIFY, LifecycleStage.MATCH,
        LifecycleStage.ALLOCATE, LifecycleStage.CONTRACT, LifecycleStage.ONBOARD,
        LifecycleStage.MOVE_IN, LifecycleStage.ACTIVE, LifecycleStage.CARE,
        LifecycleStage.RENEWAL, LifecycleStage.EXIT,
    ]

    @transaction.atomic
    def post(self, request, id):
        try:
            record = LifecycleRecord.objects.select_for_update().get(pk=id)
        except LifecycleRecord.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        to_stage = request.data.get("stage", "").strip().upper()
        description = request.data.get("description", "").strip()

        if not to_stage or to_stage not in LifecycleStage.values:
            return Response(
                {"detail": f"stage must be one of: {', '.join(LifecycleStage.values)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from_stage = record.current_stage
        LifecycleEvent.objects.create(
            record=record,
            from_stage=from_stage,
            to_stage=to_stage,
            description=description,
            created_by=request.user,
        )
        record.current_stage = to_stage
        record.stage_entered_at = timezone.now()
        record.save(update_fields=["current_stage", "stage_entered_at"])

        AuditLog.objects.create(
            actor=request.user,
            action="LIFECYCLE_ADVANCE",
            target_type="LifecycleRecord",
            target_id=str(record.id),
            metadata={"from": from_stage, "to": to_stage},
        )
        return Response(LifecycleRecordSerializer(record).data)


class MyLifecycleRecordView(APIView):
    """Student views their own lifecycle record."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        record = LifecycleRecord.objects.filter(
            student=request.user
        ).prefetch_related("events").order_by("-created_at").first()
        if not record:
            return Response({"detail": "No lifecycle record found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(LifecycleRecordSerializer(record).data)


# ═══════════════════════════════════════════════════════════════════
# STEP 9 — ASSIST SUGGESTION PANEL
# ═══════════════════════════════════════════════════════════════════

class AssistSuggestionSerializer(serializers.ModelSerializer):
    reviewed_by_email = serializers.CharField(source="reviewed_by.email", read_only=True, default=None)

    class Meta:
        model = AssistSuggestion
        fields = [
            "id", "suggestion_type", "title", "body", "confidence_score",
            "status", "application", "tenancy",
            "reviewed_by", "reviewed_by_email", "reviewed_at", "reviewer_notes",
            "created_at",
        ]
        read_only_fields = [
            "id", "reviewed_by_email", "reviewed_at", "created_at",
        ]


class AssistSuggestionListCreateView(generics.ListCreateAPIView):
    """Admin lists suggestions. System/admin can create DRAFT suggestions."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = AssistSuggestionSerializer

    def get_queryset(self):
        qs = AssistSuggestion.objects.select_related(
            "reviewed_by", "application", "tenancy"
        ).order_by("-created_at")
        s = self.request.query_params.get("status", "").strip().upper()
        t = self.request.query_params.get("type", "").strip().upper()
        if s:
            qs = qs.filter(status=s)
        if t:
            qs = qs.filter(suggestion_type=t)
        return qs

    def perform_create(self, serializer):
        # Always start at DRAFT — never auto-approved
        serializer.save(status=SuggestionStatus.DRAFT)


class AssistSuggestionReviewView(APIView):
    """Admin approves or rejects a suggestion. Human-in-the-loop: required."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def post(self, request, id, action):
        try:
            suggestion = AssistSuggestion.objects.get(pk=id)
        except AssistSuggestion.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if suggestion.status in [SuggestionStatus.APPROVED, SuggestionStatus.REJECTED]:
            return Response(
                {"detail": f"Suggestion already {suggestion.status.lower()}."},
                status=status.HTTP_409_CONFLICT,
            )

        reviewer_notes = request.data.get("reviewer_notes", "").strip()

        if action == "approve":
            suggestion.status = SuggestionStatus.APPROVED
        elif action == "reject":
            suggestion.status = SuggestionStatus.REJECTED
        else:
            return Response(
                {"detail": "action must be approve or reject."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suggestion.reviewed_by = request.user
        suggestion.reviewed_at = timezone.now()
        suggestion.reviewer_notes = reviewer_notes
        suggestion.save(update_fields=["status", "reviewed_by", "reviewed_at", "reviewer_notes"])

        AuditLog.objects.create(
            actor=request.user,
            action=f"SUGGESTION_{action.upper()}",
            target_type="AssistSuggestion",
            target_id=str(suggestion.id),
            metadata={"type": suggestion.suggestion_type, "notes": reviewer_notes},
        )
        return Response(AssistSuggestionSerializer(suggestion).data)
