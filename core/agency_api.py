import logging

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from rest_framework import generics, serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminOrStaff
from .models import (
    AgencyPartner,
    AgencyPartnerStatus,
    AgencyReferral,
    AgencyReferralStatus,
    ReferralCommission,
    CommissionStatus,
)

logger = logging.getLogger(__name__)


# ── Serializers ──────────────────────────────────────────────────────────────

class AgencyPartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgencyPartner
        fields = [
            "id", "name", "contact_email", "contact_phone", "address",
            "commission_rate", "status", "api_key", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "api_key", "created_at", "updated_at"]


class AgencyReferralSerializer(serializers.ModelSerializer):
    agency_name = serializers.CharField(source="agency.name", read_only=True)
    commission_status = serializers.CharField(source="commission.status", read_only=True, default=None)

    class Meta:
        model = AgencyReferral
        fields = [
            "id", "agency", "agency_name", "student_user", "application",
            "referral_code", "student_name", "student_email", "student_phone",
            "notes", "status", "submitted_at", "updated_at",
            "commission_status",
        ]
        read_only_fields = ["id", "referral_code", "submitted_at", "updated_at", "commission_status"]


class ReferralCommissionSerializer(serializers.ModelSerializer):
    referral_code = serializers.CharField(source="referral.referral_code", read_only=True)
    agency_name = serializers.CharField(source="referral.agency.name", read_only=True)
    student_email = serializers.CharField(source="referral.student_email", read_only=True)

    class Meta:
        model = ReferralCommission
        fields = [
            "id", "referral", "referral_code", "agency_name", "student_email",
            "amount", "currency", "status", "notes",
            "created_at", "payable_at", "paid_at",
        ]
        read_only_fields = ["id", "referral_code", "agency_name", "student_email", "created_at"]


# ── Agency Partner Views ─────────────────────────────────────────────────────

class AgencyPartnerListCreateView(generics.ListCreateAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = AgencyPartnerSerializer

    def get_queryset(self):
        qs = AgencyPartner.objects.order_by("-created_at")
        s = self.request.query_params.get("status", "").strip().upper()
        q = self.request.query_params.get("q", "").strip()
        if s:
            qs = qs.filter(status=s)
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(contact_email__icontains=q))
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AgencyPartnerDetailView(generics.RetrieveUpdateAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = AgencyPartnerSerializer
    queryset = AgencyPartner.objects.all()
    lookup_field = "id"


class AgencyPartnerActivateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def post(self, request, id):
        try:
            partner = AgencyPartner.objects.get(pk=id)
        except AgencyPartner.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        partner.status = AgencyPartnerStatus.ACTIVE
        partner.save(update_fields=["status", "updated_at"])
        return Response({"detail": "Partner activated.", "status": partner.status})

    def delete(self, request, id):
        try:
            partner = AgencyPartner.objects.get(pk=id)
        except AgencyPartner.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        partner.status = AgencyPartnerStatus.SUSPENDED
        partner.save(update_fields=["status", "updated_at"])
        return Response({"detail": "Partner suspended.", "status": partner.status})


# ── Referral Views ───────────────────────────────────────────────────────────

class AgencyReferralListCreateView(generics.ListCreateAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = AgencyReferralSerializer

    def get_queryset(self):
        qs = AgencyReferral.objects.select_related(
            "agency", "student_user", "application", "commission"
        ).order_by("-submitted_at")

        agency_id = self.request.query_params.get("agency", "").strip()
        s = self.request.query_params.get("status", "").strip().upper()
        q = self.request.query_params.get("q", "").strip()

        if agency_id:
            qs = qs.filter(agency_id=agency_id)
        if s:
            qs = qs.filter(status=s)
        if q:
            qs = qs.filter(
                Q(student_email__icontains=q) |
                Q(student_name__icontains=q) |
                Q(referral_code__icontains=q)
            )
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        referral = serializer.save()
        # Auto-create commission record at PENDING
        ReferralCommission.objects.create(
            referral=referral,
            amount=0,
            status=CommissionStatus.PENDING,
        )


class AgencyReferralDetailView(generics.RetrieveUpdateAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = AgencyReferralSerializer
    queryset = AgencyReferral.objects.select_related("agency", "commission")
    lookup_field = "id"


# ── Commission Views ─────────────────────────────────────────────────────────

class ReferralCommissionListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    serializer_class = ReferralCommissionSerializer

    def get_queryset(self):
        qs = ReferralCommission.objects.select_related(
            "referral", "referral__agency"
        ).order_by("-created_at")

        s = self.request.query_params.get("status", "").strip().upper()
        agency_id = self.request.query_params.get("agency", "").strip()
        if s:
            qs = qs.filter(status=s)
        if agency_id:
            qs = qs.filter(referral__agency_id=agency_id)
        return qs


class ReferralCommissionMarkPayableView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def post(self, request, id):
        try:
            commission = ReferralCommission.objects.get(pk=id)
        except ReferralCommission.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if commission.status != CommissionStatus.PENDING:
            return Response(
                {"detail": f"Commission is already {commission.status}."},
                status=status.HTTP_409_CONFLICT,
            )
        amount = request.data.get("amount")
        if amount is not None:
            commission.amount = amount
        commission.status = CommissionStatus.PAYABLE
        commission.payable_at = timezone.now()
        commission.notes = request.data.get("notes", commission.notes)
        commission.save(update_fields=["status", "amount", "payable_at", "notes"])
        return Response({"detail": "Commission marked as payable.", "status": commission.status})


class ReferralCommissionMarkPaidView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def post(self, request, id):
        try:
            commission = ReferralCommission.objects.select_for_update().get(pk=id)
        except ReferralCommission.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if commission.status != CommissionStatus.PAYABLE:
            return Response(
                {"detail": "Commission must be PAYABLE before marking as paid."},
                status=status.HTTP_409_CONFLICT,
            )
        commission.status = CommissionStatus.PAID
        commission.paid_at = timezone.now()
        commission.paid_by = request.user
        commission.notes = request.data.get("notes", commission.notes)
        commission.save(update_fields=["status", "paid_at", "paid_by", "notes"])

        # Advance referral to COMPLETED
        commission.referral.status = AgencyReferralStatus.COMPLETED
        commission.referral.save(update_fields=["status", "updated_at"])

        return Response({"detail": "Commission marked as paid.", "status": commission.status})


# ── Agency Dashboard Summary ─────────────────────────────────────────────────

class AgencyDashboardView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        partners_total = AgencyPartner.objects.count()
        partners_active = AgencyPartner.objects.filter(status=AgencyPartnerStatus.ACTIVE).count()

        referrals_qs = AgencyReferral.objects.values("status").annotate(count=Count("id"))
        referral_counts = {r["status"]: r["count"] for r in referrals_qs}

        commissions = ReferralCommission.objects.aggregate(
            pending_count=Count("id", filter=Q(status=CommissionStatus.PENDING)),
            payable_count=Count("id", filter=Q(status=CommissionStatus.PAYABLE)),
            paid_count=Count("id", filter=Q(status=CommissionStatus.PAID)),
            total_paid=Sum("amount", filter=Q(status=CommissionStatus.PAID)),
            total_payable=Sum("amount", filter=Q(status=CommissionStatus.PAYABLE)),
        )

        return Response({
            "partners": {"total": partners_total, "active": partners_active},
            "referrals": referral_counts,
            "commissions": {
                "pending": commissions["pending_count"] or 0,
                "payable": commissions["payable_count"] or 0,
                "paid": commissions["paid_count"] or 0,
                "total_paid_gbp": str(commissions["total_paid"] or 0),
                "total_payable_gbp": str(commissions["total_payable"] or 0),
            },
        })
