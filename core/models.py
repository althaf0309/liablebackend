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


def private_care_attachment_path(instance, filename):
    return f"care-attachments/{instance.ticket_id}/{uuid.uuid4()}-{filename}"


def private_support_attachment_path(instance, filename):
    return f"support-attachments/{instance.support_request_id}/{uuid.uuid4()}-{filename}"

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
    rule_version = models.CharField(max_length=30, default="QM-Y1-1")
    score_breakdown = models.JSONField(default=dict, blank=True)
    hard_fail_reasons = models.JSONField(default=list, blank=True)
    student_rationale = models.JSONField(default=list, blank=True)

    generated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["rank", "-confidence_score"]
        unique_together = [("user", "property")]
        indexes = [
            models.Index(fields=["user", "rank"]),
            models.Index(fields=["eligible"]),
            models.Index(fields=["rule_version"]),
            models.Index(fields=["generated_at"]),
        ]

    def __str__(self):
        return f"Match #{self.rank} {self.user.email} -> {self.property.title}"


class PropMatchScoreHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="propmatch_score_history")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="propmatch_score_history")
    rule_version = models.CharField(max_length=30, default="QM-Y1-1")
    rank = models.PositiveIntegerField(null=True, blank=True)
    confidence_score = models.PositiveIntegerField(default=0)
    eligible = models.BooleanField(default=False)
    budget_pass = models.BooleanField(default=False)
    availability_pass = models.BooleanField(default=False)
    isra_pass = models.BooleanField(default=False)
    occupancy_pass = models.BooleanField(default=False)
    score_breakdown = models.JSONField(default=dict, blank=True)
    hard_fail_reasons = models.JSONField(default=list, blank=True)
    admin_rationale = models.JSONField(default=dict, blank=True)
    student_rationale = models.JSONField(default=list, blank=True)
    generated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-generated_at", "rank", "-confidence_score"]
        indexes = [
            models.Index(fields=["user", "generated_at"]),
            models.Index(fields=["property", "generated_at"]),
            models.Index(fields=["rule_version"]),
            models.Index(fields=["eligible"]),
        ]


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


class ApplicationEntryStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    IN_REVIEW = "IN_REVIEW", "In Review"
    RETURNED = "RETURNED", "Returned for Update"
    READY = "READY", "Ready for Verification"


class ApplicationIntakeSource(models.TextChoices):
    STUDENT_PORTAL = "STUDENT_PORTAL", "Student Portal"
    ADMIN_CREATED = "ADMIN_CREATED", "Admin Created"
    PROPMATCH_LOCK = "PROPMATCH_LOCK", "PropMatch Lock"
    CONTACT_CONVERSION = "CONTACT_CONVERSION", "Contact Conversion"


class HousingApplication(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application_code = models.CharField(max_length=32, unique=True, null=True, blank=True)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="housing_applications")
    property = models.ForeignKey(Property, null=True, blank=True, on_delete=models.SET_NULL, related_name="housing_applications")
    prop_match = models.ForeignKey(PropMatchResult, null=True, blank=True, on_delete=models.SET_NULL, related_name="housing_applications")

    entry_status = models.CharField(max_length=30, choices=ApplicationEntryStatus.choices, default=ApplicationEntryStatus.SUBMITTED)
    intake_source = models.CharField(max_length=30, choices=ApplicationIntakeSource.choices, default=ApplicationIntakeSource.STUDENT_PORTAL)
    applicant_notes = models.TextField(blank=True)
    admin_entry_notes = models.TextField(blank=True)
    intake_snapshot = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    entry_reviewed_at = models.DateTimeField(null=True, blank=True)

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
            models.Index(fields=["entry_status"]),
            models.Index(fields=["intake_source"]),
            models.Index(fields=["updated_at"]),
        ]

    def __str__(self):
        return f"{self.application_code or self.user.email} - {self.stage}"

    def save(self, *args, **kwargs):
        if not self.application_code:
            self.application_code = f"QL-{timezone.now():%Y%m%d}-{str(self.id)[:8].upper()}"
        if not self.submitted_at and self.entry_status != ApplicationEntryStatus.DRAFT:
            self.submitted_at = timezone.now()
        super().save(*args, **kwargs)


class TimelineEventType(models.TextChoices):
    APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED", "Application Submitted"
    ENTRY_REVIEWED = "ENTRY_REVIEWED", "Entry Reviewed"
    VERIFICATION_READY = "VERIFICATION_READY", "Verification Ready"
    STAGE_CHANGED = "STAGE_CHANGED", "Stage Changed"
    MATCHING_STARTED = "MATCHING_STARTED", "Matching Started"
    PROPERTY_LOCKED = "PROPERTY_LOCKED", "Property Locked"
    MOVE_IN_SCHEDULED = "MOVE_IN_SCHEDULED", "Move-in Scheduled"
    CARE_TICKET_OPENED = "CARE_TICKET_OPENED", "Care Ticket Opened"
    SUPPORT_REQUEST_OPENED = "SUPPORT_REQUEST_OPENED", "Support Request Opened"
    RENEWAL_REMINDER = "RENEWAL_REMINDER", "Renewal Reminder"
    COMPLETED = "COMPLETED", "Completed"


class NotificationAudience(models.TextChoices):
    STUDENT = "STUDENT", "Student"
    LANDLORD = "LANDLORD", "Landlord"
    STAFF = "STAFF", "Staff"
    ADMIN = "ADMIN", "Admin"


class ApplicationTimelineEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(HousingApplication, on_delete=models.CASCADE, related_name="timeline_events")
    event_type = models.CharField(max_length=40, choices=TimelineEventType.choices, default=TimelineEventType.STAGE_CHANGED)
    from_stage = models.CharField(max_length=30, blank=True)
    to_stage = models.CharField(max_length=30, blank=True)
    actor = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="application_timeline_events")
    student_message = models.CharField(max_length=240)
    admin_message = models.CharField(max_length=360, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["application", "created_at"]),
            models.Index(fields=["event_type"]),
            models.Index(fields=["to_stage"]),
        ]


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notifications")
    application = models.ForeignKey(HousingApplication, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    timeline_event = models.ForeignKey(ApplicationTimelineEvent, null=True, blank=True, on_delete=models.SET_NULL, related_name="notifications")
    audience = models.CharField(max_length=20, choices=NotificationAudience.choices)
    title = models.CharField(max_length=140)
    message = models.CharField(max_length=360)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "read_at"]),
            models.Index(fields=["application", "created_at"]),
            models.Index(fields=["audience"]),
        ]


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
    CARE_TICKET_OPENED = "CARE_TICKET_OPENED", "Care Ticket Opened"
    CARE_TICKET_RESOLVED = "CARE_TICKET_RESOLVED", "Care Ticket Resolved"
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


class CareTicketCategory(models.TextChoices):
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    SAFETY = "SAFETY", "Safety"
    ACCESS = "ACCESS", "Access"
    UTILITIES = "UTILITIES", "Utilities"
    MOVE_IN = "MOVE_IN", "Move-in Issue"
    PROPERTY_CARE = "PROPERTY_CARE", "Property Care"
    OTHER = "OTHER", "Other"


class CareTicketStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    TRIAGED = "TRIAGED", "Triaged"
    ASSIGNED = "ASSIGNED", "Assigned"
    WAITING_LANDLORD = "WAITING_LANDLORD", "Waiting Landlord"
    WAITING_TENANT = "WAITING_TENANT", "Waiting Tenant"
    RESOLVED = "RESOLVED", "Resolved"
    CLOSED = "CLOSED", "Closed"


class CareTicketPriority(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"
    URGENT = "URGENT", "Urgent"


class CareTicketEventType(models.TextChoices):
    CREATED = "CREATED", "Created"
    STATUS_CHANGED = "STATUS_CHANGED", "Status Changed"
    ASSIGNED = "ASSIGNED", "Assigned"
    LANDLORD_UPDATED = "LANDLORD_UPDATED", "Landlord Updated"
    TENANT_UPDATED = "TENANT_UPDATED", "Tenant Updated"
    RESOLVED = "RESOLVED", "Resolved"
    CLOSED = "CLOSED", "Closed"


class MalwareScanStatus(models.TextChoices):
    NOT_REQUIRED = "NOT_REQUIRED", "Not Required"
    PENDING = "PENDING", "Pending"
    CLEAN = "CLEAN", "Clean"
    FAILED = "FAILED", "Failed"
    INFECTED = "INFECTED", "Infected"


class CareTicket(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="care_tickets")
    property = models.ForeignKey(Property, on_delete=models.PROTECT, related_name="care_tickets")
    tenancy = models.ForeignKey(Tenancy, null=True, blank=True, on_delete=models.SET_NULL, related_name="care_tickets")
    application = models.ForeignKey(HousingApplication, null=True, blank=True, on_delete=models.SET_NULL, related_name="care_tickets")
    assigned_to = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_care_tickets",
    )
    category = models.CharField(max_length=30, choices=CareTicketCategory.choices, default=CareTicketCategory.MAINTENANCE)
    priority = models.CharField(max_length=20, choices=CareTicketPriority.choices, default=CareTicketPriority.MEDIUM)
    status = models.CharField(max_length=30, choices=CareTicketStatus.choices, default=CareTicketStatus.OPEN)
    title = models.CharField(max_length=180)
    description = models.TextField()
    student_safe_summary = models.CharField(max_length=240, blank=True)
    landlord_visible = models.BooleanField(default=True)
    internal_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["property", "status"]),
            models.Index(fields=["tenancy", "status"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["category", "priority"]),
            models.Index(fields=["created_at"]),
        ]


class CareTicketEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(CareTicket, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=30, choices=CareTicketEventType.choices, default=CareTicketEventType.CREATED)
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30, blank=True)
    actor = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="care_ticket_events")
    student_message = models.CharField(max_length=240)
    landlord_message = models.CharField(max_length=240, blank=True)
    admin_message = models.CharField(max_length=360, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["ticket", "created_at"]),
            models.Index(fields=["event_type"]),
            models.Index(fields=["to_status"]),
        ]


class CareTicketAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(CareTicket, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="care_ticket_attachments")
    file = models.FileField(upload_to=private_care_attachment_path)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    malware_scan_status = models.CharField(max_length=20, choices=MalwareScanStatus.choices, default=MalwareScanStatus.NOT_REQUIRED)
    malware_scanned_at = models.DateTimeField(null=True, blank=True)
    malware_scan_details = models.CharField(max_length=240, blank=True)
    landlord_visible = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["ticket"]),
            models.Index(fields=["uploaded_by"]),
            models.Index(fields=["malware_scan_status"]),
            models.Index(fields=["uploaded_at"]),
        ]


class SupportRequestCategory(models.TextChoices):
    NHS_GUIDANCE = "NHS_GUIDANCE", "NHS Guidance"
    BANKING_GUIDANCE = "BANKING_GUIDANCE", "Banking Guidance"
    ATS_CV_SUPPORT = "ATS_CV_SUPPORT", "ATS/CV Support"
    AIRPORT_PICKUP = "AIRPORT_PICKUP", "Airport Pickup"
    SETTLEMENT_SUPPORT = "SETTLEMENT_SUPPORT", "Settlement Support"
    UNIVERSITY_COMMUNITY = "UNIVERSITY_COMMUNITY", "University/Community Guidance"
    GENERAL_SUPPORT = "GENERAL_SUPPORT", "General Support"


class SupportRequestStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    TRIAGED = "TRIAGED", "Triaged"
    ASSIGNED = "ASSIGNED", "Assigned"
    WAITING_STUDENT = "WAITING_STUDENT", "Waiting Student"
    WAITING_PARTNER = "WAITING_PARTNER", "Waiting Partner"
    RESOLVED = "RESOLVED", "Resolved"
    CLOSED = "CLOSED", "Closed"


class SupportRequestPriority(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"
    URGENT = "URGENT", "Urgent"


class SupportRequestEventType(models.TextChoices):
    CREATED = "CREATED", "Created"
    STATUS_CHANGED = "STATUS_CHANGED", "Status Changed"
    ASSIGNED = "ASSIGNED", "Assigned"
    STUDENT_UPDATED = "STUDENT_UPDATED", "Student Updated"
    PARTNER_UPDATED = "PARTNER_UPDATED", "Partner Updated"
    RESOLVED = "RESOLVED", "Resolved"
    CLOSED = "CLOSED", "Closed"


class SupportRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="support_requests")
    application = models.ForeignKey(HousingApplication, null=True, blank=True, on_delete=models.SET_NULL, related_name="support_requests")
    assigned_to = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_support_requests",
    )
    category = models.CharField(max_length=40, choices=SupportRequestCategory.choices, default=SupportRequestCategory.GENERAL_SUPPORT)
    priority = models.CharField(max_length=20, choices=SupportRequestPriority.choices, default=SupportRequestPriority.MEDIUM)
    status = models.CharField(max_length=30, choices=SupportRequestStatus.choices, default=SupportRequestStatus.OPEN)
    title = models.CharField(max_length=180)
    description = models.TextField()
    student_safe_summary = models.CharField(max_length=240, blank=True)
    partner_visible = models.BooleanField(default=False)
    internal_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["application", "status"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["category", "priority"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.user.email}"


class SupportRequestEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    support_request = models.ForeignKey(SupportRequest, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=30, choices=SupportRequestEventType.choices, default=SupportRequestEventType.CREATED)
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30, blank=True)
    actor = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="support_request_events")
    student_message = models.CharField(max_length=240)
    admin_message = models.CharField(max_length=360, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["support_request", "created_at"]),
            models.Index(fields=["event_type"]),
            models.Index(fields=["to_status"]),
        ]


class SupportRequestAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    support_request = models.ForeignKey(SupportRequest, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="support_request_attachments")
    file = models.FileField(upload_to=private_support_attachment_path)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    malware_scan_status = models.CharField(max_length=20, choices=MalwareScanStatus.choices, default=MalwareScanStatus.NOT_REQUIRED)
    malware_scanned_at = models.DateTimeField(null=True, blank=True)
    malware_scan_details = models.CharField(max_length=240, blank=True)
    partner_visible = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["support_request"]),
            models.Index(fields=["uploaded_by"]),
            models.Index(fields=["malware_scan_status"]),
            models.Index(fields=["uploaded_at"]),
        ]


class AssistReminderType(models.TextChoices):
    DOCUMENT_EXPIRY = "DOCUMENT_EXPIRY", "Document Expiry"
    MOVE_IN = "MOVE_IN", "Move-in"
    RENT_DUE = "RENT_DUE", "Rent Due"
    CARE_FOLLOW_UP = "CARE_FOLLOW_UP", "Care Follow-up"
    SUPPORT_FOLLOW_UP = "SUPPORT_FOLLOW_UP", "Support Follow-up"
    RENEWAL = "RENEWAL", "Renewal"
    GENERAL = "GENERAL", "General"


class AssistReminderStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    SENT = "SENT", "Sent"
    COMPLETED = "COMPLETED", "Completed"
    DISMISSED = "DISMISSED", "Dismissed"
    CANCELLED = "CANCELLED", "Cancelled"


class AssistReminderPriority(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"


class AssistAutomationAction(models.TextChoices):
    CREATED = "CREATED", "Created"
    DUE_PROCESSED = "DUE_PROCESSED", "Due Processed"
    NOTIFICATION_SENT = "NOTIFICATION_SENT", "Notification Sent"
    COMPLETED = "COMPLETED", "Completed"
    DISMISSED = "DISMISSED", "Dismissed"
    CANCELLED = "CANCELLED", "Cancelled"


class AssistReminder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="assist_reminders")
    application = models.ForeignKey(HousingApplication, null=True, blank=True, on_delete=models.SET_NULL, related_name="assist_reminders")
    tenancy = models.ForeignKey(Tenancy, null=True, blank=True, on_delete=models.SET_NULL, related_name="assist_reminders")
    care_ticket = models.ForeignKey(CareTicket, null=True, blank=True, on_delete=models.SET_NULL, related_name="assist_reminders")
    support_request = models.ForeignKey(SupportRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name="assist_reminders")
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_assist_reminders",
    )
    assigned_to = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_assist_reminders",
    )
    reminder_type = models.CharField(max_length=30, choices=AssistReminderType.choices, default=AssistReminderType.GENERAL)
    priority = models.CharField(max_length=20, choices=AssistReminderPriority.choices, default=AssistReminderPriority.MEDIUM)
    status = models.CharField(max_length=20, choices=AssistReminderStatus.choices, default=AssistReminderStatus.SCHEDULED)
    title = models.CharField(max_length=180)
    student_message = models.CharField(max_length=240)
    internal_notes = models.TextField(blank=True)
    due_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["application", "status"]),
            models.Index(fields=["tenancy", "status"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["reminder_type", "priority"]),
            models.Index(fields=["due_at", "status"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.user.email}"


class AssistAutomationLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reminder = models.ForeignKey(AssistReminder, on_delete=models.CASCADE, related_name="automation_logs")
    action = models.CharField(max_length=30, choices=AssistAutomationAction.choices)
    actor = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="assist_automation_logs")
    message = models.CharField(max_length=360)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["reminder", "created_at"]),
            models.Index(fields=["action"]),
        ]


class StudentDocumentType(models.TextChoices):
    VISA = "VISA", "Visa"
    PROOF_OF_FUNDS = "PROOF_OF_FUNDS", "Proof of Funds"
    UNIVERSITY_CERTIFICATE = "UNIVERSITY_CERTIFICATE", "University Certificate"
    IDENTITY = "IDENTITY", "Identity"
    PASSPORT = "PASSPORT", "Passport"
    RIGHT_TO_RENT = "RIGHT_TO_RENT", "Right to Rent"
    GUARANTOR_OR_SPONSOR = "GUARANTOR_OR_SPONSOR", "Guarantor or Sponsor Letter"
    ADDRESS_HISTORY = "ADDRESS_HISTORY", "Address History"
    EMERGENCY_CONTACT = "EMERGENCY_CONTACT", "Emergency Contact"
    OTHER = "OTHER", "Other"


class VerificationState(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    RESUBMISSION_REQUIRED = "RESUBMISSION_REQUIRED", "Resubmission Required"
    EXPIRED = "EXPIRED", "Expired"


class DocumentRequirementStage(models.TextChoices):
    ENTRY = "ENTRY", "Entry"
    VERIFICATION = "VERIFICATION", "Verification"
    MOVE_IN = "MOVE_IN", "Move-in"


class StudentDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="student_documents")
    application = models.ForeignKey(
        HousingApplication,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="student_documents",
    )
    document_type = models.CharField(max_length=40, choices=StudentDocumentType.choices, default=StudentDocumentType.OTHER)
    requirement_stage = models.CharField(max_length=30, choices=DocumentRequirementStage.choices, default=DocumentRequirementStage.VERIFICATION)
    file = models.FileField(upload_to=private_document_path)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    malware_scan_status = models.CharField(max_length=20, choices=MalwareScanStatus.choices, default=MalwareScanStatus.NOT_REQUIRED)
    malware_scanned_at = models.DateTimeField(null=True, blank=True)
    malware_scan_details = models.CharField(max_length=240, blank=True)
    verification_status = models.CharField(max_length=30, choices=VerificationState.choices, default=VerificationState.PENDING)
    expiry_date = models.DateField(null=True, blank=True)
    resubmission_requested_at = models.DateTimeField(null=True, blank=True)
    student_message = models.CharField(max_length=240, blank=True)
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

    # Retention: set when tenancy ends. Documents purged after this date.
    # PASSPORT/VISA = tenancy_end + 365 days; others = 180 days post-application close.
    retained_until = models.DateTimeField(null=True, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "document_type"]),
            models.Index(fields=["application", "document_type"]),
            models.Index(fields=["requirement_stage"]),
            models.Index(fields=["verification_status"]),
            models.Index(fields=["malware_scan_status"]),
            models.Index(fields=["expiry_date"]),
            models.Index(fields=["uploaded_at"]),
            models.Index(fields=["retained_until"]),
        ]


class ComplaintAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=private_complaint_attachment_path)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    malware_scan_status = models.CharField(max_length=20, choices=MalwareScanStatus.choices, default=MalwareScanStatus.NOT_REQUIRED)
    malware_scanned_at = models.DateTimeField(null=True, blank=True)
    malware_scan_details = models.CharField(max_length=240, blank=True)
    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["complaint"]),
            models.Index(fields=["malware_scan_status"]),
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


# ── AGENCY PARTNER SYSTEM ────────────────────────────────────────────────────

class AgencyPartnerStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"
    PENDING = "PENDING", "Pending Approval"


class AgencyPartner(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    contact_email = models.EmailField(unique=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    # Commission rate as decimal — e.g. 0.05 = 5%
    commission_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0.05)
    status = models.CharField(max_length=20, choices=AgencyPartnerStatus.choices, default=AgencyPartnerStatus.PENDING)
    api_key = models.CharField(max_length=64, unique=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="created_agency_partners"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def save(self, *args, **kwargs):
        if not self.api_key:
            import secrets as _secrets
            self.api_key = _secrets.token_hex(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.status})"


class AgencyReferralStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    INTAKE = "INTAKE", "Intake Registered"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    TENANCY_ACTIVE = "TENANCY_ACTIVE", "Tenancy Active"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class AgencyReferral(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agency = models.ForeignKey(AgencyPartner, on_delete=models.CASCADE, related_name="referrals")
    student_user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="agency_referrals"
    )
    application = models.ForeignKey(
        HousingApplication, null=True, blank=True, on_delete=models.SET_NULL, related_name="agency_referral"
    )
    referral_code = models.CharField(max_length=40, unique=True)
    student_name = models.CharField(max_length=150)
    student_email = models.EmailField()
    student_phone = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=AgencyReferralStatus.choices, default=AgencyReferralStatus.SUBMITTED)
    submitted_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["agency", "status"]),
            models.Index(fields=["referral_code"]),
            models.Index(fields=["submitted_at"]),
        ]

    def save(self, *args, **kwargs):
        if not self.referral_code:
            import secrets as _secrets
            self.referral_code = f"AGY-{_secrets.token_hex(6).upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.referral_code} — {self.student_email}"


class CommissionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PAYABLE = "PAYABLE", "Payable"
    PAID = "PAID", "Paid"
    CANCELLED = "CANCELLED", "Cancelled"


class ReferralCommission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    referral = models.OneToOneField(AgencyReferral, on_delete=models.CASCADE, related_name="commission")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="GBP")
    status = models.CharField(max_length=20, choices=CommissionStatus.choices, default=CommissionStatus.PENDING)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    payable_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="paid_commissions"
    )

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Commission {self.referral.referral_code}: £{self.amount} ({self.status})"


# ── BOOKING HOLD ─────────────────────────────────────────────────────────────

class BookingHoldStatus(models.TextChoices):
    REQUESTED = "REQUESTED", "Requested"
    ADMIN_REVIEW = "ADMIN_REVIEW", "Admin Review"
    APPROVED = "APPROVED", "Approved"
    PROPERTY_RESERVED = "PROPERTY_RESERVED", "Property Reserved"
    REJECTED = "REJECTED", "Rejected"
    EXPIRED = "EXPIRED", "Expired"
    CANCELLED = "CANCELLED", "Cancelled"


class BookingHold(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="booking_holds"
    )
    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name="booking_holds"
    )
    application = models.ForeignKey(
        HousingApplication, null=True, blank=True, on_delete=models.SET_NULL, related_name="booking_holds"
    )
    status = models.CharField(
        max_length=20, choices=BookingHoldStatus.choices, default=BookingHoldStatus.REQUESTED
    )
    student_notes = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_booking_holds"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    requested_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["property", "status"]),
            models.Index(fields=["status"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"Hold({self.student_id}, {self.property_id}, {self.status})"


# ── TENANCY CONTRACT RECORD ──────────────────────────────────────────────────

class ContractFieldStatus(models.TextChoices):
    NOT_STARTED = "NOT_STARTED", "Not Started"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    COMPLETE = "COMPLETE", "Complete"
    FAILED = "FAILED", "Failed"


class TenancyContractRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenancy = models.OneToOneField(
        Tenancy, on_delete=models.CASCADE, related_name="contract_record"
    )
    agreement_status = models.CharField(
        max_length=20, choices=ContractFieldStatus.choices, default=ContractFieldStatus.NOT_STARTED
    )
    right_to_rent_status = models.CharField(
        max_length=20, choices=ContractFieldStatus.choices, default=ContractFieldStatus.NOT_STARTED
    )
    inventory_status = models.CharField(
        max_length=20, choices=ContractFieldStatus.choices, default=ContractFieldStatus.NOT_STARTED
    )
    deposit_status = models.CharField(
        max_length=20, choices=ContractFieldStatus.choices, default=ContractFieldStatus.NOT_STARTED
    )
    notes = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="updated_contract_records"
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["tenancy"])]

    def __str__(self):
        return f"ContractRecord(tenancy={self.tenancy_id})"


# ── WORKFLOW TASK QUEUE ──────────────────────────────────────────────────────

class WorkflowTaskType(models.TextChoices):
    VERIFY_DOCUMENT = "VERIFY_DOCUMENT", "Verify Document"
    CONFIRM_MATCH = "CONFIRM_MATCH", "Confirm Match"
    ISSUE_CONTRACT = "ISSUE_CONTRACT", "Issue Contract"
    SCHEDULE_INSPECTION = "SCHEDULE_INSPECTION", "Schedule Inspection"
    RESOLVE_COMPLAINT = "RESOLVE_COMPLAINT", "Resolve Complaint"
    PROCESS_RENEWAL = "PROCESS_RENEWAL", "Process Renewal"
    REVIEW_HOLD = "REVIEW_HOLD", "Review Booking Hold"
    OTHER = "OTHER", "Other"


class WorkflowTaskStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    BLOCKED = "BLOCKED", "Blocked"
    DONE = "DONE", "Done"
    CANCELLED = "CANCELLED", "Cancelled"


class WorkflowTaskPriority(models.TextChoices):
    LOW = "LOW", "Low"
    NORMAL = "NORMAL", "Normal"
    HIGH = "HIGH", "High"
    URGENT = "URGENT", "Urgent"


class WorkflowTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_type = models.CharField(
        max_length=30, choices=WorkflowTaskType.choices, default=WorkflowTaskType.OTHER
    )
    title = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=WorkflowTaskStatus.choices, default=WorkflowTaskStatus.OPEN
    )
    priority = models.CharField(
        max_length=10, choices=WorkflowTaskPriority.choices, default=WorkflowTaskPriority.NORMAL
    )
    assigned_to = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_tasks"
    )
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="created_tasks"
    )
    application = models.ForeignKey(
        HousingApplication, null=True, blank=True, on_delete=models.SET_NULL, related_name="workflow_tasks"
    )
    tenancy = models.ForeignKey(
        Tenancy, null=True, blank=True, on_delete=models.SET_NULL, related_name="workflow_tasks"
    )
    due_date = models.DateTimeField(null=True, blank=True)
    blocked_reason = models.CharField(max_length=500, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["due_date"]),
            models.Index(fields=["task_type"]),
        ]

    def __str__(self):
        return f"[{self.priority}] {self.title} ({self.status})"


# ── LIFECYCLE RECORD ─────────────────────────────────────────────────────────

class LifecycleStage(models.TextChoices):
    INQUIRY = "INQUIRY", "Inquiry"
    VERIFY = "VERIFY", "Verify"
    MATCH = "MATCH", "Match"
    ALLOCATE = "ALLOCATE", "Allocate"
    CONTRACT = "CONTRACT", "Contract"
    ONBOARD = "ONBOARD", "Onboard"
    MOVE_IN = "MOVE_IN", "Move In"
    ACTIVE = "ACTIVE", "Active"
    CARE = "CARE", "Care"
    RENEWAL = "RENEWAL", "Renewal"
    EXIT = "EXIT", "Exit"


class LifecycleRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="lifecycle_records"
    )
    current_stage = models.CharField(
        max_length=20, choices=LifecycleStage.choices, default=LifecycleStage.INQUIRY
    )
    application = models.ForeignKey(
        HousingApplication, null=True, blank=True, on_delete=models.SET_NULL, related_name="lifecycle_record"
    )
    tenancy = models.ForeignKey(
        Tenancy, null=True, blank=True, on_delete=models.SET_NULL, related_name="lifecycle_record"
    )
    agency_referral = models.ForeignKey(
        AgencyReferral, null=True, blank=True, on_delete=models.SET_NULL, related_name="lifecycle_record"
    )
    notes = models.TextField(blank=True)
    stage_entered_at = models.DateTimeField(default=timezone.now)
    last_updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["student", "current_stage"]),
            models.Index(fields=["current_stage"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Lifecycle({self.student_id}, {self.current_stage})"


class LifecycleEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(LifecycleRecord, on_delete=models.CASCADE, related_name="events")
    from_stage = models.CharField(max_length=20, choices=LifecycleStage.choices, blank=True)
    to_stage = models.CharField(max_length=20, choices=LifecycleStage.choices)
    description = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="lifecycle_events"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["record", "created_at"]),
        ]


# ── ASSIST SUGGESTION ────────────────────────────────────────────────────────

class SuggestionType(models.TextChoices):
    MATCH_PROPERTY = "MATCH_PROPERTY", "Match Property"
    ESCALATE_COMPLAINT = "ESCALATE_COMPLAINT", "Escalate Complaint"
    SCHEDULE_RENEWAL = "SCHEDULE_RENEWAL", "Schedule Renewal"
    FLAG_RISK = "FLAG_RISK", "Flag Risk"
    SEND_REMINDER = "SEND_REMINDER", "Send Reminder"
    OTHER = "OTHER", "Other"


class SuggestionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    REVIEWED = "REVIEWED", "Reviewed"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class AssistSuggestion(models.Model):
    """Human-reviewed AI suggestion. Never auto-approved — operator must act."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    suggestion_type = models.CharField(
        max_length=30, choices=SuggestionType.choices, default=SuggestionType.OTHER
    )
    title = models.CharField(max_length=250)
    body = models.TextField()
    confidence_score = models.FloatField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=SuggestionStatus.choices, default=SuggestionStatus.DRAFT
    )
    application = models.ForeignKey(
        HousingApplication, null=True, blank=True, on_delete=models.SET_NULL, related_name="assist_suggestions"
    )
    tenancy = models.ForeignKey(
        Tenancy, null=True, blank=True, on_delete=models.SET_NULL, related_name="assist_suggestions"
    )
    reviewed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_suggestions"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["suggestion_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"[{self.suggestion_type}] {self.title} ({self.status})"
