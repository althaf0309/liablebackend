# core/admin.py
from django.contrib import admin
from .models import *


class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 0
    fields = ("sort_order", "is_cover", "image_url", "alt_text", "caption", "created_at")
    readonly_fields = ("created_at",)
    ordering = ("sort_order",)


class PropertyVideoInline(admin.TabularInline):
    model = PropertyVideo
    extra = 0
    fields = ("sort_order", "is_featured", "provider", "title", "video_url", "thumbnail_url", "created_at")
    readonly_fields = ("created_at",)
    ordering = ("sort_order",)


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = (
        "title", "city", "locality", "status",
        "rent_monthly", "currency",
        "is_featured", "priority_rank", "assigned_landlord", "isra_threshold",
        "map_pin_verified", "created_at"
    )
    list_filter = (
        "status", "city", "property_type", "room_type",
        "is_featured", "map_pin_verified", "created_at"
    )
    search_fields = ("title", "slug", "city", "locality", "address_line1", "postal_code")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("-created_at",)

    fieldsets = (
        ("Identity", {"fields": ("title", "slug", "description", "status")}),
        ("Type & Layout", {"fields": ("property_type", "room_type", "bedrooms", "bathrooms", "area_sqft", "furnish_status")}),
        ("Pricing", {"fields": ("currency", "rent_monthly", "deposit_amount", "maintenance_amount", "bills_included")}),
        ("Availability", {"fields": ("available_from", "min_stay_months", "max_stay_months")}),
        ("Location", {"fields": (
            "country", "state", "city", "locality",
            "address_line1", "address_line2", "postal_code",
            "latitude", "longitude", "map_pin_verified"
        )}),
        ("Amenities", {"fields": (
            "has_wifi", "has_ac", "has_parking", "has_gym", "has_pool",
            "has_lift", "has_power_backup", "has_security", "has_cctv", "has_washing_machine"
        )}),
        ("Rules", {"fields": ("smoking_allowed", "pets_allowed", "alcohol_allowed", "guests_allowed")}),
        ("Media quick pointers", {"fields": ("cover_image_url", "featured_video_url")}),
        ("Operator / Internal", {"fields": ("created_by", "assigned_landlord", "is_featured", "priority_rank", "isra_threshold", "internal_notes")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    inlines = [PropertyImageInline, PropertyVideoInline]


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_published", "published_at", "created_at")
    list_filter = ("is_published", "created_at")
    search_fields = ("title", "slug", "excerpt")
    readonly_fields = ("id", "created_at")
    ordering = ("-created_at",)

    fieldsets = (
        ("Post", {"fields": ("slug", "title", "excerpt", "content")}),
        ("Publishing", {"fields": ("is_published", "published_at")}),
        ("Audit", {"fields": ("created_at",)}),
    )


@admin.register(PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin):
    list_display = ("property", "sort_order", "is_cover", "image_url", "created_at")
    list_filter = ("is_cover", "created_at")
    search_fields = ("property__title", "image_url", "alt_text", "caption")
    readonly_fields = ("created_at",)
    ordering = ("property", "sort_order")


@admin.register(PropertyVideo)
class PropertyVideoAdmin(admin.ModelAdmin):
    list_display = ("property", "sort_order", "is_featured", "provider", "video_url", "created_at")
    list_filter = ("provider", "is_featured", "created_at")
    search_fields = ("property__title", "video_url", "title")
    readonly_fields = ("created_at",)
    ordering = ("property", "sort_order")

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "contact_type", "created_at")
    list_filter = ("contact_type", "created_at")
    search_fields = ("name", "email", "message")
    readonly_fields = ("name", "email", "contact_type", "message", "created_at")
    ordering = ("-created_at",)


@admin.register(IntentForm)
class IntentFormAdmin(admin.ModelAdmin):
    list_display = ("user", "city", "budget_max", "university", "move_in_date", "updated_at")
    list_filter = ("identity", "purpose", "city", "proof_of_funds_verified")
    search_fields = ("user__email", "user__full_name", "city", "university")


@admin.register(ISRAscore)
class ISRAscoreAdmin(admin.ModelAdmin):
    list_display = ("user", "total_score", "risk_band", "recommended_max_rent", "override_applied", "updated_at")
    list_filter = ("risk_band", "override_applied")
    search_fields = ("user__email", "user__full_name")


@admin.register(PropMatchResult)
class PropMatchResultAdmin(admin.ModelAdmin):
    list_display = ("user", "property", "rank", "confidence_score", "eligible", "generated_at")
    list_filter = ("eligible", "budget_pass", "isra_pass", "availability_pass")
    search_fields = ("user__email", "property__title")


@admin.register(Tenancy)
class TenancyAdmin(admin.ModelAdmin):
    list_display = ("user", "property", "status", "start_date", "end_date", "rent_amount")
    list_filter = ("status", "deposit_status")
    search_fields = ("user__email", "property__title")


@admin.register(TenancyHealthScore)
class TenancyHealthScoreAdmin(admin.ModelAdmin):
    list_display = ("tenancy", "score", "band", "trend", "calculated_at")
    list_filter = ("band", "trend")
    search_fields = ("tenancy__user__email", "tenancy__property__title")


@admin.register(TenancyHealthEvent)
class TenancyHealthEventAdmin(admin.ModelAdmin):
    list_display = ("tenancy", "event_type", "weight", "occurred_at")
    list_filter = ("event_type",)
    search_fields = ("tenancy__user__email", "tenancy__property__title", "note")


@admin.register(TenancyRecord)
class TenancyRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "property", "badge_label", "outcome", "ths_score_snapshot", "certificate_code", "issued_at")
    search_fields = ("user__email", "property__title", "certificate_code")


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "property", "status", "created_at")
    list_filter = ("status", "category")
    search_fields = ("title", "user__email", "property__title")


@admin.register(StudentDocument)
class StudentDocumentAdmin(admin.ModelAdmin):
    list_display = ("user", "document_type", "original_filename", "verification_status", "uploaded_at")
    list_filter = ("document_type", "verification_status")
    search_fields = ("user__email", "user__full_name", "original_filename")


@admin.register(ComplaintAttachment)
class ComplaintAttachmentAdmin(admin.ModelAdmin):
    list_display = ("complaint", "original_filename", "content_type", "file_size", "uploaded_at")
    search_fields = ("complaint__title", "complaint__user__email", "original_filename")


@admin.register(PropertyExpense)
class PropertyExpenseAdmin(admin.ModelAdmin):
    list_display = ("property", "landlord", "category", "amount", "incurred_on")
    list_filter = ("category",)
    search_fields = ("property__title", "landlord__email")


@admin.register(RentLedger)
class RentLedgerAdmin(admin.ModelAdmin):
    list_display = ("tenancy", "due_date", "rent_amount", "utility_amount", "paid_amount", "status")
    list_filter = ("status",)


@admin.register(YOEMetric)
class YOEMetricAdmin(admin.ModelAdmin):
    list_display = ("property", "landlord", "gross_yield", "net_yield", "occupancy_rate", "rent_collection_rate", "calculated_at")
    list_filter = ("landlord", "calculated_at")
    search_fields = ("property__title", "landlord__email")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("actor", "action", "target_type", "target_id", "created_at")
    list_filter = ("action", "target_type")
    search_fields = ("action", "target_type", "target_id", "actor__email")
