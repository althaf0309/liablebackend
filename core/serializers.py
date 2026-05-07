from rest_framework import serializers
from .models import *


class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = ["id", "image_url", "alt_text", "caption", "is_cover", "sort_order"]


class PropertyVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyVideo
        fields = ["id", "provider", "title", "video_url", "thumbnail_url", "is_featured", "sort_order"]


class PublicPropertyListSerializer(serializers.ModelSerializer):
    images = PropertyImageSerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = [
            "id", "slug", "title", "description",
            "city", "locality",
            "property_type", "room_type",
            "bedrooms", "bathrooms", "area_sqft",
            "currency", "rent_monthly",
            "status", "available_from",
            "is_featured", "priority_rank",
            "isra_threshold",
            "images",
        ]


class PublicPropertyDetailSerializer(serializers.ModelSerializer):
    images = PropertyImageSerializer(many=True, read_only=True)
    videos = PropertyVideoSerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = [
            "id", "slug", "title", "description",

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

            "is_featured", "priority_rank",
            "isra_threshold",

            "images", "videos",
            "created_at", "updated_at",
        ]


class PublicBlogListSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogPost
        fields = ["id", "slug", "title", "excerpt", "published_at"]


class PublicBlogDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogPost
        fields = ["id", "slug", "title", "excerpt", "content", "published_at"]

class ContactMessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ["name", "phone", "email", "subject", "contact_type","message"]

    def validate_name(self, v):
        v = (v or "").strip()
        if not v:
            raise serializers.ValidationError("Name is required.")
        return v

    def validate_message(self, v):
        v = (v or "").strip()
        if not v:
            raise serializers.ValidationError("Message is required.")
        return v


class IntentFormSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = IntentForm
        fields = [
            "id", "user", "user_email", "user_name",
            "identity", "purpose", "room_type",
            "budget_min", "budget_max",
            "city", "preferred_locality",
            "university", "course", "nationality",
            "visa_type", "visa_expiry", "proof_of_funds_verified",
            "move_in_date", "lifestyle_preferences",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ISRAscoreSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    intent_form = IntentFormSerializer(source="user.intent_form", read_only=True)

    class Meta:
        model = ISRAscore
        fields = [
            "id", "user", "user_email", "user_name", "intent_form",
            "stability_score", "financial_score", "behavioural_score",
            "total_score", "risk_band", "recommended_max_rent",
            "notes", "flags", "override_applied", "override_reason",
            "calculated_at", "updated_at",
        ]
        read_only_fields = ["id", "total_score", "risk_band", "recommended_max_rent", "calculated_at", "updated_at"]


class StudentISRAsummarySerializer(serializers.ModelSerializer):
    tier = serializers.CharField(source="risk_band", read_only=True)
    improvement_tips = serializers.SerializerMethodField()

    class Meta:
        model = ISRAscore
        fields = [
            "id", "tier", "recommended_max_rent",
            "improvement_tips", "calculated_at", "updated_at",
        ]
        read_only_fields = fields

    def get_improvement_tips(self, obj):
        tips = []
        intent = getattr(obj.user, "intent_form", None)
        if intent and not intent.proof_of_funds_verified:
            tips.append("Upload proof of funds to strengthen your financial signal.")
        if intent and not intent.visa_expiry:
            tips.append("Add visa duration details to improve stability confidence.")
        if obj.recommended_max_rent and intent and intent.budget_max > obj.recommended_max_rent:
            tips.append("Keep rent choices within the recommended maximum rent.")
        if not tips:
            tips.append("Keep rent payments and tenancy communication consistent.")
        return tips[:3]


class PropMatchResultSerializer(serializers.ModelSerializer):
    property = PublicPropertyListSerializer(read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = PropMatchResult
        fields = [
            "id", "user", "user_email", "user_name",
            "property", "rank", "confidence_score",
            "budget_pass", "availability_pass", "isra_pass", "eligible",
            "rationale", "generated_at",
        ]
        read_only_fields = fields


class TenancySerializer(serializers.ModelSerializer):
    property_title = serializers.CharField(source="property.title", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Tenancy
        fields = [
            "id", "user", "user_email", "property", "property_title",
            "start_date", "end_date", "rent_amount", "deposit_amount",
            "status", "deposit_status", "extension_requested",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TenancyHealthEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenancyHealthEvent
        fields = ["id", "tenancy", "event_type", "weight", "note", "occurred_at", "created_at"]
        read_only_fields = fields


class TenancyHealthScoreSerializer(serializers.ModelSerializer):
    tenancy_property = serializers.CharField(source="tenancy.property.title", read_only=True)
    tenant_email = serializers.EmailField(source="tenancy.user.email", read_only=True)
    events = TenancyHealthEventSerializer(source="tenancy.health_events", many=True, read_only=True)

    class Meta:
        model = TenancyHealthScore
        fields = [
            "id", "tenancy", "tenancy_property", "tenant_email",
            "score", "band", "rent_signal", "complaint_signal",
            "communication_signal", "trend", "summary",
            "reason_codes", "policy_version",
            "calculated_at", "updated_at", "events",
        ]
        read_only_fields = fields


class TenancyRecordSerializer(serializers.ModelSerializer):
    property_title = serializers.CharField(source="property.title", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    certificate_url = serializers.SerializerMethodField()

    class Meta:
        model = TenancyRecord
        fields = [
            "id", "user", "user_email", "tenancy", "property", "property_title",
            "badge_label", "outcome", "ths_score_snapshot",
            "certificate_code", "issued_at", "certificate_url",
        ]
        read_only_fields = fields

    def get_certificate_url(self, obj):
        return f"/api/core/tenancy-records/{obj.id}/certificate/"


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id", "actor", "actor_email", "action", "target_type",
            "target_id", "metadata", "created_at",
        ]
        read_only_fields = fields


class ComplaintSerializer(serializers.ModelSerializer):
    property_title = serializers.CharField(source="property.title", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    attachment_count = serializers.IntegerField(source="attachments.count", read_only=True)

    class Meta:
        model = Complaint
        fields = [
            "id", "user", "user_email", "property", "property_title",
            "title", "category", "description", "status", "admin_notes",
            "resolved_at", "attachment_count", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "user": {"required": False},
            "status": {"required": False},
            "admin_notes": {"required": False},
        }


class LandlordComplaintSerializer(serializers.ModelSerializer):
    property_title = serializers.CharField(source="property.title", read_only=True)

    class Meta:
        model = Complaint
        fields = [
            "id", "property", "property_title",
            "title", "category", "status",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class StudentDocumentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = StudentDocument
        fields = [
            "id", "user", "user_email", "user_name", "document_type", "original_filename", "content_type",
            "file_size", "verification_status", "admin_notes",
            "uploaded_at", "reviewed_at", "download_url",
        ]
        read_only_fields = [
            "id", "user", "original_filename", "content_type", "file_size",
            "uploaded_at", "reviewed_at", "download_url",
        ]

    def get_download_url(self, obj):
        return f"/api/core/documents/{obj.id}/download/"


class ComplaintAttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ComplaintAttachment
        fields = [
            "id", "complaint", "original_filename", "content_type",
            "file_size", "uploaded_at", "download_url",
        ]
        read_only_fields = fields

    def get_download_url(self, obj):
        return f"/api/core/complaint-attachments/{obj.id}/download/"


class PropertyExpenseSerializer(serializers.ModelSerializer):
    property_title = serializers.CharField(source="property.title", read_only=True)
    landlord_email = serializers.EmailField(source="landlord.email", read_only=True)

    class Meta:
        model = PropertyExpense
        fields = [
            "id", "property", "property_title", "landlord", "landlord_email",
            "category", "amount", "description", "incurred_on", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class YOEMetricSerializer(serializers.ModelSerializer):
    property_title = serializers.CharField(source="property.title", read_only=True)
    landlord_email = serializers.EmailField(source="landlord.email", read_only=True)

    class Meta:
        model = YOEMetric
        fields = [
            "id", "property", "property_title", "landlord", "landlord_email",
            "property_value", "annual_rent", "annual_expenses",
            "occupancy_rate", "gross_yield", "net_yield",
            "rent_collection_rate", "active_tenancies", "open_complaints",
            "recommendation", "calculated_at", "updated_at",
        ]
        read_only_fields = [
            "id", "property_title", "landlord_email", "annual_rent",
            "annual_expenses", "occupancy_rate", "gross_yield", "net_yield",
            "rent_collection_rate", "active_tenancies", "open_complaints",
            "recommendation", "calculated_at", "updated_at",
        ]


class RentLedgerSerializer(serializers.ModelSerializer):
    tenant_email = serializers.EmailField(source="tenancy.user.email", read_only=True)
    property_title = serializers.CharField(source="tenancy.property.title", read_only=True)

    class Meta:
        model = RentLedger
        fields = [
            "id", "tenancy", "tenant_email", "property_title",
            "due_date", "rent_amount", "utility_amount", "paid_amount",
            "status", "paid_at", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class LandlordRentLedgerSerializer(serializers.ModelSerializer):
    property_title = serializers.CharField(source="tenancy.property.title", read_only=True)

    class Meta:
        model = RentLedger
        fields = [
            "id", "property_title",
            "due_date", "rent_amount", "utility_amount", "paid_amount",
            "status", "paid_at", "created_at",
        ]
        read_only_fields = fields
