# core/models.py
import uuid
from django.db import models
from django.utils import timezone
import logging
logger = logging.getLogger(__name__)


def private_document_path(instance, filename):
    return f"student-documents/{instance.user_id}/{uuid.uuid4()}-{filename}"


def private_complaint_attachment_path(instance, filename):
    return f"complaint-attachments/{instance.complaint_id}/{uuid.uuid4()}-{filename}"

# ------------------- BLOG -------------------
class BlogPost(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    slug = models.SlugField(unique=True, max_length=220)
    title = models.CharField(max_length=220)
    excerpt = models.TextField(blank=True)
    content = models.TextField()

    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_published"]),
        ]

    def __str__(self):
        return self.title


# ------------------- PROPERTY -------------------
class PropertyStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    APPROVED = "APPROVED", "Approved"
    SUSPENDED = "SUSPENDED", "Suspended"
    RENTED = "RENTED", "Rented"


class FurnishStatus(models.TextChoices):
    UNFURNISHED = "UNFURNISHED", "Unfurnished"
    SEMI = "SEMI", "Semi-Furnished"
    FULL = "FULL", "Fully Furnished"


class PropertyType(models.TextChoices):
    APARTMENT = "APARTMENT", "Apartment"
    VILLA = "VILLA", "Villa"
    STUDIO = "STUDIO", "Studio"
    PG = "PG", "PG/Hostel"
    TOWNHOUSE = "TOWNHOUSE", "Townhouse"
    OTHER = "OTHER", "Other"


class RoomType(models.TextChoices):
    PRIVATE = "PRIVATE", "Private Room"
    SHARED = "SHARED", "Shared Room"
    ENTIRE = "ENTIRE", "Entire Unit"


class Property(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # identity
    title = models.CharField(max_length=220)
    slug = models.SlugField(max_length=260, unique=True)
    description = models.TextField(blank=True)

    # type / layout
    property_type = models.CharField(max_length=30, choices=PropertyType.choices, default=PropertyType.APARTMENT)
    room_type = models.CharField(max_length=30, choices=RoomType.choices, default=RoomType.ENTIRE)
    bedrooms = models.PositiveIntegerField(default=0)
    bathrooms = models.PositiveIntegerField(default=0)
    area_sqft = models.PositiveIntegerField(null=True, blank=True)

    # pricing
    currency = models.CharField(max_length=10, default="INR")
    rent_monthly = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    maintenance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bills_included = models.BooleanField(default=False)

    # availability
    status = models.CharField(max_length=20, choices=PropertyStatus.choices, default=PropertyStatus.DRAFT)
    available_from = models.DateField(null=True, blank=True)
    min_stay_months = models.PositiveIntegerField(default=1)
    max_stay_months = models.PositiveIntegerField(null=True, blank=True)

    # location
    country = models.CharField(max_length=120, default="India")
    state = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120)
    locality = models.CharField(max_length=140, blank=True)
    address_line1 = models.CharField(max_length=240, blank=True)
    address_line2 = models.CharField(max_length=240, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    map_pin_verified = models.BooleanField(default=False)

    # furnishing & amenities
    furnish_status = models.CharField(max_length=20, choices=FurnishStatus.choices, default=FurnishStatus.SEMI)

    has_wifi = models.BooleanField(default=False)
    has_ac = models.BooleanField(default=False)
    has_parking = models.BooleanField(default=False)
    has_gym = models.BooleanField(default=False)
    has_pool = models.BooleanField(default=False)
    has_lift = models.BooleanField(default=False)
    has_power_backup = models.BooleanField(default=False)
    has_security = models.BooleanField(default=False)
    has_cctv = models.BooleanField(default=False)
    has_washing_machine = models.BooleanField(default=False)

    # rules
    smoking_allowed = models.BooleanField(default=False)
    pets_allowed = models.BooleanField(default=False)
    alcohol_allowed = models.BooleanField(default=False)
    guests_allowed = models.BooleanField(default=True)

    # quick pointers (optional, still useful)
    cover_image_url = models.URLField(blank=True)
    featured_video_url = models.URLField(blank=True)

    # operator flags
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_properties",
    )
    assigned_landlord = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_properties",
        limit_choices_to={"role": "LANDLORD"},
    )
    is_featured = models.BooleanField(default=False)
    priority_rank = models.PositiveIntegerField(default=0)
    isra_threshold = models.PositiveIntegerField(default=60)

    internal_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["city"]),
            models.Index(fields=["locality"]),
            models.Index(fields=["rent_monthly"]),
            models.Index(fields=["property_type"]),
            models.Index(fields=["room_type"]),
            models.Index(fields=["is_featured"]),
            models.Index(fields=["priority_rank"]),
            models.Index(fields=["assigned_landlord"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.city}"


# ------------------- PROPERTY MEDIA -------------------
class PropertyImage(models.Model):
    id = models.BigAutoField(primary_key=True)

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="images")
    image_url = models.URLField()
    alt_text = models.CharField(max_length=200, blank=True)
    caption = models.CharField(max_length=250, blank=True)

    is_cover = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["property", "sort_order"]),
            models.Index(fields=["property", "is_cover"]),
        ]


class VideoProvider(models.TextChoices):
    YOUTUBE = "YOUTUBE", "YouTube"
    VIMEO = "VIMEO", "Vimeo"
    MP4 = "MP4", "Direct MP4"
    OTHER = "OTHER", "Other"


class PropertyVideo(models.Model):
    id = models.BigAutoField(primary_key=True)

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="videos")

    provider = models.CharField(max_length=20, choices=VideoProvider.choices, default=VideoProvider.OTHER)
    title = models.CharField(max_length=200, blank=True)

    video_url = models.URLField()
    thumbnail_url = models.URLField(blank=True)

    is_featured = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["property", "sort_order"]),
            models.Index(fields=["property", "is_featured"]),
            models.Index(fields=["provider"]),
        ]


# ------------------- CONTACT -------------------
class ContactMessage(models.Model):
    CONTACT_TYPE_CHOICES = (
        ("student", "Student"),
        ("landlord", "Landlord"),
        ("tenant", "Tenant"),
        ("other", "Other"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=100)
    email = models.EmailField(max_length=255)

    phone = models.CharField(max_length=20, blank=True)
    subject = models.CharField(max_length=200, blank=True)

    # ✅ REQUIRED FOR HOMEPAGE FORM
    contact_type = models.CharField(
        max_length=20,
        choices=CONTACT_TYPE_CHOICES,
        blank=True
    )

    message = models.TextField(max_length=1000)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["contact_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.email}"

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)

        if creating:
            try:
                from accounts.email_utils import email_contact_message_admin
                email_contact_message_admin(
                    name=self.name,
                    email=self.email,
                    phone=self.phone,
                    subject=self.subject,
                    message=self.message,
                    created_at=self.created_at,
                )
            except Exception as e:
                # ✅ Don’t break API if email fails
                logger.exception("ContactMessage email failed: %s", e)


class IntentIdentity(models.TextChoices):
    STUDENT = "STUDENT", "Student"
    WORKING = "WORKING", "Working Professional"
    COUPLE = "COUPLE", "Couple"


class IntentPurpose(models.TextChoices):
    STUDY = "STUDY", "Study"
    WORK = "WORK", "Work"
    BOTH = "BOTH", "Both"
    SHORT_STAY = "SHORT_STAY", "Short-term Stay"


class IntentForm(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="intent_form")

    identity = models.CharField(max_length=30, choices=IntentIdentity.choices, default=IntentIdentity.STUDENT)
    purpose = models.CharField(max_length=30, choices=IntentPurpose.choices, default=IntentPurpose.STUDY)
    room_type = models.CharField(max_length=80)
    budget_min = models.PositiveIntegerField(default=0)
    budget_max = models.PositiveIntegerField(default=0)
    city = models.CharField(max_length=120)
    preferred_locality = models.CharField(max_length=160, blank=True)
    university = models.CharField(max_length=200, blank=True)
    course = models.CharField(max_length=200, blank=True)
    nationality = models.CharField(max_length=120, blank=True)
    visa_type = models.CharField(max_length=80, blank=True)
    visa_expiry = models.DateField(null=True, blank=True)
    proof_of_funds_verified = models.BooleanField(default=False)
    move_in_date = models.DateField(null=True, blank=True)
    lifestyle_preferences = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["city"]),
            models.Index(fields=["budget_max"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Intent - {self.user.email}"


class RiskBand(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"


class ISRAscore(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="isra_score")

    stability_score = models.PositiveIntegerField(default=0)
    financial_score = models.PositiveIntegerField(default=0)
    behavioural_score = models.PositiveIntegerField(default=0)
    total_score = models.PositiveIntegerField(default=0)
    risk_band = models.CharField(max_length=20, choices=RiskBand.choices, default=RiskBand.HIGH)
    recommended_max_rent = models.PositiveIntegerField(default=0)

    notes = models.TextField(blank=True)
    flags = models.JSONField(default=list, blank=True)
    override_applied = models.BooleanField(default=False)
    override_reason = models.TextField(blank=True)

    calculated_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ISRA score"
        verbose_name_plural = "ISRA scores"
        indexes = [
            models.Index(fields=["total_score"]),
            models.Index(fields=["risk_band"]),
            models.Index(fields=["calculated_at"]),
        ]

    def __str__(self):
        return f"ISRA {self.total_score} - {self.user.email}"


class PropMatchResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="prop_matches")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="prop_matches")

    rank = models.PositiveIntegerField(default=1)
    confidence_score = models.PositiveIntegerField(default=0)
    budget_pass = models.BooleanField(default=False)
    availability_pass = models.BooleanField(default=False)
    isra_pass = models.BooleanField(default=False)
    eligible = models.BooleanField(default=False)
    rationale = models.JSONField(default=dict, blank=True)

    generated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["rank", "-confidence_score"]
        unique_together = [("user", "property")]
        indexes = [
            models.Index(fields=["user", "rank"]),
            models.Index(fields=["eligible"]),
            models.Index(fields=["generated_at"]),
        ]

    def __str__(self):
        return f"Match #{self.rank} {self.user.email} -> {self.property.title}"


class ApplicationStage(models.TextChoices):
    APPLICATION = "APPLICATION", "Application"
    VERIFICATION = "VERIFICATION", "Verification"
    MATCHING = "MATCHING", "Matching"
    MOVE_IN = "MOVE_IN", "Move-in"
    CARE = "CARE", "Care"
    SUPPORT = "SUPPORT", "Support"
    RENEWAL = "RENEWAL", "Renewal"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class ApplicationStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    PAUSED = "PAUSED", "Paused"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class HousingApplication(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="housing_applications")
    property = models.ForeignKey(Property, null=True, blank=True, on_delete=models.SET_NULL, related_name="housing_applications")
    prop_match = models.ForeignKey(PropMatchResult, null=True, blank=True, on_delete=models.SET_NULL, related_name="housing_applications")

    stage = models.CharField(max_length=30, choices=ApplicationStage.choices, default=ApplicationStage.APPLICATION)
    status = models.CharField(max_length=20, choices=ApplicationStatus.choices, default=ApplicationStatus.ACTIVE)
    stage_notes = models.CharField(max_length=240, blank=True)
    next_action = models.CharField(max_length=240, blank=True)
    target_move_in_date = models.DateField(null=True, blank=True)
    stage_history = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "stage"]),
            models.Index(fields=["property", "stage"]),
            models.Index(fields=["status"]),
            models.Index(fields=["updated_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.stage}"


class TenancyStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ACTIVE = "ACTIVE", "Active"
    ENDED = "ENDED", "Ended"
    CANCELLED = "CANCELLED", "Cancelled"


class Tenancy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="tenancies")
    property = models.ForeignKey(Property, on_delete=models.PROTECT, related_name="tenancies")

    start_date = models.DateField()
    end_date = models.DateField()
    rent_amount = models.DecimalField(max_digits=12, decimal_places=2)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=TenancyStatus.choices, default=TenancyStatus.PENDING)
    deposit_status = models.CharField(max_length=80, blank=True)
    extension_requested = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["property", "status"]),
            models.Index(fields=["start_date"]),
        ]


class THSEventType(models.TextChoices):
    RENT_PAID_ON_TIME = "RENT_PAID_ON_TIME", "Rent Paid On Time"
    RENT_LATE = "RENT_LATE", "Rent Late"
    COMPLAINT_RAISED = "COMPLAINT_RAISED", "Complaint Raised"
    COMPLAINT_RESOLVED = "COMPLAINT_RESOLVED", "Complaint Resolved"
    ADMIN_NOTE = "ADMIN_NOTE", "Admin Note"


class TenancyHealthScore(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenancy = models.OneToOneField(Tenancy, on_delete=models.CASCADE, related_name="health_score")
    score = models.PositiveIntegerField(default=70)
    band = models.CharField(max_length=20, choices=RiskBand.choices, default=RiskBand.MEDIUM)
    rent_signal = models.PositiveIntegerField(default=70)
    complaint_signal = models.PositiveIntegerField(default=70)
    communication_signal = models.PositiveIntegerField(default=70)
    trend = models.CharField(max_length=20, default="STABLE")
    summary = models.CharField(max_length=240, blank=True)
    reason_codes = models.JSONField(default=list, blank=True)
    policy_version = models.CharField(max_length=20, default="THS-Y1-1")
    calculated_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["score"]),
            models.Index(fields=["band"]),
            models.Index(fields=["calculated_at"]),
        ]


class TenancyHealthEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenancy = models.ForeignKey(Tenancy, on_delete=models.CASCADE, related_name="health_events")
    event_type = models.CharField(max_length=40, choices=THSEventType.choices)
    weight = models.IntegerField(default=0)
    note = models.CharField(max_length=240, blank=True)
    source_type = models.CharField(max_length=40, blank=True)
    source_id = models.CharField(max_length=80, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("source_type", "source_id", "event_type")]
        indexes = [
            models.Index(fields=["tenancy", "occurred_at"]),
            models.Index(fields=["event_type"]),
        ]


class TenancyRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="tenancy_records")
    tenancy = models.OneToOneField(Tenancy, on_delete=models.CASCADE, related_name="portable_record")
    property = models.ForeignKey(Property, on_delete=models.PROTECT, related_name="tenancy_records")
    badge_label = models.CharField(max_length=120, default="Verified Tenant")
    outcome = models.CharField(max_length=120, default="Completed Successfully")
    ths_score_snapshot = models.PositiveIntegerField(default=0)
    certificate_code = models.CharField(max_length=40, unique=True)
    issued_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["user", "issued_at"]),
            models.Index(fields=["certificate_code"]),
        ]


class ComplaintStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    RESOLVED = "RESOLVED", "Resolved"


class Complaint(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="complaints")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="complaints")
    title = models.CharField(max_length=180)
    category = models.CharField(max_length=80, blank=True)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=ComplaintStatus.choices, default=ComplaintStatus.OPEN)
    admin_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["property", "status"]),
            models.Index(fields=["created_at"]),
        ]


class StudentDocumentType(models.TextChoices):
    VISA = "VISA", "Visa"
    PROOF_OF_FUNDS = "PROOF_OF_FUNDS", "Proof of Funds"
    UNIVERSITY_CERTIFICATE = "UNIVERSITY_CERTIFICATE", "University Certificate"
    IDENTITY = "IDENTITY", "Identity"
    OTHER = "OTHER", "Other"


class VerificationState(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class StudentDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="student_documents")
    document_type = models.CharField(max_length=40, choices=StudentDocumentType.choices, default=StudentDocumentType.OTHER)
    file = models.FileField(upload_to=private_document_path)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    verification_status = models.CharField(max_length=20, choices=VerificationState.choices, default=VerificationState.PENDING)
    admin_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_student_documents",
    )
    uploaded_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "document_type"]),
            models.Index(fields=["verification_status"]),
            models.Index(fields=["uploaded_at"]),
        ]


class ComplaintAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=private_complaint_attachment_path)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["complaint"]),
            models.Index(fields=["uploaded_at"]),
        ]


class ExpenseCategory(models.TextChoices):
    RENOVATION = "RENOVATION", "Renovation"
    FURNITURE = "FURNITURE", "Furniture"
    REPAIRS = "REPAIRS", "Repairs"
    OTHER = "OTHER", "Other"


class PropertyExpense(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="expenses")
    landlord = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="property_expenses",
    )
    category = models.CharField(max_length=30, choices=ExpenseCategory.choices, default=ExpenseCategory.OTHER)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=240, blank=True)
    incurred_on = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["property", "category"]),
            models.Index(fields=["landlord"]),
            models.Index(fields=["incurred_on"]),
        ]


class YOEMetric(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="yoe_metric")
    landlord = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="yoe_metrics",
    )

    property_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    annual_rent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    annual_expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    occupancy_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    gross_yield = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    net_yield = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    rent_collection_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    active_tenancies = models.PositiveIntegerField(default=0)
    open_complaints = models.PositiveIntegerField(default=0)
    recommendation = models.CharField(max_length=240, blank=True)

    calculated_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "YOE metric"
        verbose_name_plural = "YOE metrics"
        indexes = [
            models.Index(fields=["landlord"]),
            models.Index(fields=["net_yield"]),
            models.Index(fields=["calculated_at"]),
        ]

    def __str__(self):
        return f"YOE {self.net_yield}% - {self.property.title}"


class RentLedgerStatus(models.TextChoices):
    DUE = "DUE", "Due"
    PAID = "PAID", "Paid"
    OVERDUE = "OVERDUE", "Overdue"


class RentLedger(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenancy = models.ForeignKey(Tenancy, on_delete=models.CASCADE, related_name="rent_ledger")
    due_date = models.DateField()
    rent_amount = models.DecimalField(max_digits=12, decimal_places=2)
    utility_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=RentLedgerStatus.choices, default=RentLedgerStatus.DUE)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["due_date"]),
            models.Index(fields=["status"]),
        ]


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    actor = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs")
    action = models.CharField(max_length=120)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=80, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["action"]),
            models.Index(fields=["created_at"]),
        ]
