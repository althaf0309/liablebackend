import uuid
import secrets
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password

class UserRole(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    STAFF = "STAFF", "Staff"
    LANDLORD = "LANDLORD", "Landlord"
    STUDENT = "STUDENT", "Student"

class VerificationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", UserRole.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("verification_status", VerificationStatus.APPROVED)
        extra_fields.setdefault("verified_at", timezone.now())
        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.STUDENT)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        "self", null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="created_users"
    )

    created_at = models.DateTimeField(default=timezone.now)
    last_login_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["verification_status"]),
        ]

    def __str__(self):
        return f"{self.email} ({self.role})"

    @staticmethod
    def generate_temp_password(length: int = 10) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#"
        return "".join(secrets.choice(alphabet) for _ in range(length))

class LoginAudit(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    email_attempted = models.EmailField(blank=True)
    success = models.BooleanField(default=False)
    failure_reason = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["success"]),
            models.Index(fields=["ip_address"]),
        ]

class VisitorHit(models.Model):
    id = models.BigAutoField(primary_key=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    path = models.CharField(max_length=500)
    referrer = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["ip_address"]),
        ]

class LandlordProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="landlord_profile")

    property_address = models.CharField(max_length=300, blank=True)
    property_type = models.CharField(max_length=80, blank=True)
    number_of_properties = models.CharField(max_length=50, blank=True)
    bedrooms = models.CharField(max_length=20, blank=True)
    current_status = models.CharField(max_length=80, blank=True)
    expected_rent = models.CharField(max_length=40, blank=True)
    services_required = models.CharField(max_length=80, blank=True)
    additional_info = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["created_at"])]

class StudentProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile")

    nationality = models.CharField(max_length=120, blank=True)
    university = models.CharField(max_length=200, blank=True)
    course = models.CharField(max_length=200, blank=True)
    arrival_date = models.DateField(null=True, blank=True)
    accommodation_type = models.CharField(max_length=80, blank=True)
    budget = models.CharField(max_length=80, blank=True)
    services_needed = models.CharField(max_length=120, blank=True)
    additional_info = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["created_at"])]

class Question(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    target_role = models.CharField(max_length=20, choices=UserRole.choices)
    question_text = models.CharField(max_length=400)
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["target_role", "is_active", "sort_order"])]

class Answer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    answer_text = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("user", "question")]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["user"]),
        ]

class PasswordResetOTP(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_reset_otps")
    otp_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(default=timezone.now)
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
        ]

    @staticmethod
    def generate_otp() -> str:
        return f"{secrets.randbelow(10**6):06d}"

    @classmethod
    def create_for_user(cls, user, otp: str):
        return cls.objects.create(user=user, otp_hash=make_password(otp))

    def verify(self, otp: str) -> bool:
        return check_password(otp, self.otp_hash)


class ErasureStatus(models.TextChoices):
    REQUESTED = "REQUESTED", "Requested"
    ADMIN_REVIEW = "ADMIN_REVIEW", "Admin Review"
    EXECUTED = "EXECUTED", "Executed"
    REJECTED = "REJECTED", "Rejected"


class DataErasureRequest(models.Model):
    """GDPR Article 17 right-to-erasure request. Admin must execute manually."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="erasure_requests",
    )
    user_email_snapshot = models.EmailField()
    reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=ErasureStatus.choices, default=ErasureStatus.REQUESTED
    )
    requested_at = models.DateTimeField(default=timezone.now)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_erasure_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["requested_at"]),
        ]

    def __str__(self):
        return f"ErasureRequest({self.user_email_snapshot}, {self.status})"
