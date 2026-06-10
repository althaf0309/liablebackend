import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from rest_framework import generics, serializers
from rest_framework.authentication import SessionAuthentication

from .models import (
    LandlordProfile,
    StudentProfile,
    User,
    UserRole,
    VerificationStatus,
)
from .permissions import IsAdminOrStaff
from .serializers import (
    LandlordProfileSerializer,
    StudentProfileSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)


class AdminUserWriteSerializer(serializers.ModelSerializer):
    landlord_profile = LandlordProfileSerializer(required=False)
    student_profile = StudentProfileSerializer(required=False)
    password = serializers.CharField(write_only=True, required=False, min_length=6)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "password",
            "full_name",
            "phone",
            "role",
            "is_active",
            "verification_status",
            "landlord_profile",
            "student_profile",
            "created_at",
            "verified_at",
        ]
        read_only_fields = ["id", "created_at", "verified_at"]

    def validate(self, attrs):
        request = self.context["request"]
        actor = request.user
        role = attrs.get("role", getattr(self.instance, "role", None))

        if actor.role != UserRole.ADMIN and role in [UserRole.ADMIN, UserRole.STAFF]:
            raise serializers.ValidationError("Only admin can create or update ADMIN/STAFF users.")

        if role == UserRole.LANDLORD and "student_profile" in attrs:
            raise serializers.ValidationError("student_profile is not allowed for LANDLORD users.")

        if role == UserRole.STUDENT and "landlord_profile" in attrs:
            raise serializers.ValidationError("landlord_profile is not allowed for STUDENT users.")

        if role in [UserRole.ADMIN, UserRole.STAFF] and (
            "landlord_profile" in attrs or "student_profile" in attrs
        ):
            raise serializers.ValidationError("Profiles are only supported for LANDLORD or STUDENT users.")

        return attrs

    def _apply_role_flags(self, user, role, verification_status=None, is_active=None):
        if role == UserRole.ADMIN:
            user.is_staff = True
            user.is_superuser = True
        elif role == UserRole.STAFF:
            user.is_staff = True
            user.is_superuser = False
        else:
            user.is_staff = False
            user.is_superuser = False

        if is_active is None:
            user.is_active = True
        else:
            user.is_active = is_active

        final_status = verification_status or VerificationStatus.APPROVED
        user.verification_status = final_status
        user.verified_at = timezone.now() if final_status == VerificationStatus.APPROVED else None

    def _sync_profiles(self, user, role, landlord_data=None, student_data=None):
        if role == UserRole.LANDLORD:
            if student_data is not None or hasattr(user, "student_profile"):
                StudentProfile.objects.filter(user=user).delete()
            if landlord_data is not None:
                profile, _ = LandlordProfile.objects.get_or_create(user=user)
                for field, value in landlord_data.items():
                    setattr(profile, field, value)
                profile.save()
        elif role == UserRole.STUDENT:
            if landlord_data is not None or hasattr(user, "landlord_profile"):
                LandlordProfile.objects.filter(user=user).delete()
            if student_data is not None:
                profile, _ = StudentProfile.objects.get_or_create(user=user)
                for field, value in student_data.items():
                    setattr(profile, field, value)
                profile.save()
        else:
            LandlordProfile.objects.filter(user=user).delete()
            StudentProfile.objects.filter(user=user).delete()

    @transaction.atomic
    def create(self, validated_data):
        landlord_data = validated_data.pop("landlord_profile", None)
        student_data = validated_data.pop("student_profile", None)
        password = validated_data.pop("password", None)
        role = validated_data["role"]
        is_active = validated_data.pop("is_active", None)
        verification_status = validated_data.pop("verification_status", None)

        user = User(**validated_data)
        user.created_by = self.context["request"].user
        self._apply_role_flags(user, role, verification_status, is_active)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()

        self._sync_profiles(user, role, landlord_data, student_data)
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        landlord_data = validated_data.pop("landlord_profile", None)
        student_data = validated_data.pop("student_profile", None)
        password = validated_data.pop("password", None)

        role = validated_data.get("role", instance.role)
        is_active = validated_data.pop("is_active", instance.is_active)
        previous_status = instance.verification_status
        verification_status = validated_data.pop(
            "verification_status",
            instance.verification_status,
        )

        for field, value in validated_data.items():
            setattr(instance, field, value)

        self._apply_role_flags(instance, role, verification_status, is_active)

        # If admin is approving for the first time and no password supplied,
        # generate a temporary password and email login credentials.
        being_approved = (
            previous_status != VerificationStatus.APPROVED
            and verification_status == VerificationStatus.APPROVED
        )
        temp_password = None
        if being_approved and not password and not instance.has_usable_password():
            temp_password = User.generate_temp_password()
            instance.set_password(temp_password)
        elif password:
            instance.set_password(password)

        instance.save()
        self._sync_profiles(instance, role, landlord_data, student_data)

        if being_approved:
            try:
                from .email_utils import email_account_approved
                email_account_approved(
                    to_email=instance.email,
                    name=instance.full_name or instance.email,
                    login_email=instance.email,
                    temp_password=temp_password or "(password already set by admin)",
                )
            except Exception:
                logger.exception("Approval email failed for %s", instance.email)

        return instance

    def to_representation(self, instance):
        return UserSerializer(instance, context=self.context).data


class AdminUserListCreateView(generics.ListCreateAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def get_queryset(self):
        qs = (
            User.objects
            .select_related("created_by", "landlord_profile", "student_profile")
            .order_by("-created_at")
        )

        role = (self.request.query_params.get("role") or "").strip().upper()
        status_value = (self.request.query_params.get("verification_status") or "").strip().upper()
        q = (self.request.query_params.get("q") or "").strip()

        if self.request.user.role != UserRole.ADMIN:
            qs = qs.exclude(role__in=[UserRole.ADMIN, UserRole.STAFF])

        if role:
            qs = qs.filter(role=role)
        if status_value:
            qs = qs.filter(verification_status=status_value)
        if q:
            qs = qs.filter(Q(email__icontains=q) | Q(full_name__icontains=q) | Q(phone__icontains=q))
        return qs

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AdminUserWriteSerializer
        return UserSerializer


class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]
    queryset = User.objects.all()
    lookup_field = "id"

    def get_queryset(self):
        qs = User.objects.select_related("landlord_profile", "student_profile")
        if self.request.user.role != UserRole.ADMIN:
            qs = qs.exclude(role__in=[UserRole.ADMIN, UserRole.STAFF])
        return qs

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return AdminUserWriteSerializer
        return UserSerializer
