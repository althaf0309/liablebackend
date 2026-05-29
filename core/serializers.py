from rest_framework import serializers
from .models import *
from .quantum_flow import flow_progress_index, flow_stage_label


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


class HousingApplicationSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    property_title = serializers.CharField(source="property.title", read_only=True)
    stage_label = serializers.SerializerMethodField()
    progress_index = serializers.SerializerMethodField()

    class Meta:
        model = HousingApplication
        fields = [
            "id", "user", "user_email", "user_name",
            "property", "property_title", "prop_match",
            "stage", "stage_label", "status", "progress_index",
            "stage_notes", "next_action", "target_move_in_date",
            "stage_history", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "user_email", "user_name", "property_title",
            "stage_label", "progress_index", "stage_history",
            "created_at", "updated_at",
        ]

    def get_stage_label(self, obj):
        return flow_stage_label(obj.stage)

    def get_progress_index(self, obj):
        return flow_progress_index(obj.stage)


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
    indicator = serializers.SerializerMethodField()
    indicator_label = serializers.SerializerMethodField()
    support_summary = serializers.SerializerMethodField()
    tracked_signals = serializers.SerializerMethodField()

    class Meta:
        model = TenancyHealthScore
        fields = [
            "id", "tenancy", "tenancy_property", "tenant_email",
            "score", "band", "rent_signal", "complaint_signal",
            "communication_signal", "trend", "summary",
            "indicator", "indicator_label", "support_summary", "tracked_signals",
            "reason_codes", "policy_version",
            "calculated_at", "updated_at", "events",
        ]
        read_only_fields = fields

    def get_indicator(self, obj):
        if obj.band == RiskBand.LOW:
            return "HEALTHY"
        if obj.band == RiskBand.MEDIUM:
            return "STABLE"
        return "NEEDS_ATTENTION"

    def get_indicator_label(self, obj):
        if obj.band == RiskBand.LOW:
            return "Healthy"
        if obj.band == RiskBand.MEDIUM:
            return "Stable"
        return "Needs Attention"

    def get_support_summary(self, obj):
        return obj.summary

    def get_tracked_signals(self, obj):
        return [
            {"key": "rent_behaviour", "label": "Rent behaviour", "value": obj.rent_signal},
            {"key": "complaints", "label": "Complaints", "value": obj.complaint_signal},
            {"key": "communication", "label": "Communication", "value": obj.communication_signal},
            {"key": "tenancy_stability", "label": "Tenancy stability", "value": obj.score},
            {"key": "property_care", "label": "Property care", "value": obj.complaint_signal},
            {"key": "occupancy_continuity", "label": "Occupancy continuity", "value": obj.score},
        ]


class TenancyRecordSerializer(serializers.ModelSerializer):
    property_title = serializers.CharField(source="property.title", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    certificate_url = serializers.SerializerMethodField()
    includes = serializers.SerializerMethodField()
    excludes = serializers.SerializerMethodField()
    privacy_statement = serializers.SerializerMethodField()

    class Meta:
        model = TenancyRecord
        fields = [
            "id", "user", "user_email", "tenancy", "property", "property_title",
            "badge_label", "outcome", "ths_score_snapshot",
            "certificate_code", "issued_at", "certificate_url",
            "includes", "excludes", "privacy_statement",
        ]
        read_only_fields = fields

    def get_certificate_url(self, obj):
        return f"/api/core/tenancy-records/{obj.id}/certificate/"

    def get_includes(self, obj):
        return [
            "tenancy completion status",
            "tenancy duration",
            "supportive tenancy health snapshot",
            "property and occupancy completion reference",
        ]

    def get_excludes(self, obj):
        return [
            "raw complaint narratives",
            "private uploaded documents",
            "immigration details",
            "sensitive financial evidence",
        ]

    def get_privacy_statement(self, obj):
        return "This record confirms successful occupancy history without exposing sensitive student documents, raw complaint details, immigration data, or private financial evidence."


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
    reviewed_by_email = serializers.EmailField(source="reviewed_by.email", read_only=True)
    student_review_message = serializers.SerializerMethodField()

    class Meta:
        model = StudentDocument
        fields = [
            "id", "user", "user_email", "user_name", "document_type", "original_filename", "content_type",
            "file_size", "verification_status", "admin_notes",
            "reviewed_by", "reviewed_by_email", "student_review_message",
            "uploaded_at", "reviewed_at", "download_url",
        ]
        read_only_fields = [
            "id", "user", "original_filename", "content_type", "file_size",
            "reviewed_by", "reviewed_by_email", "student_review_message",
            "uploaded_at", "reviewed_at", "download_url",
        ]

    def get_download_url(self, obj):
        return f"/api/core/documents/{obj.id}/download/"

    def get_student_review_message(self, obj):
        if obj.verification_status == VerificationState.APPROVED:
            return "Document verified by LGS operations."
        if obj.verification_status == VerificationState.REJECTED:
            return "Document needs review. Please contact LGS support or upload an updated file."
        return "Document received and waiting for LGS verification."

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        is_admin_view = bool(
            user
            and getattr(user, "is_authenticated", False)
            and (getattr(user, "is_superuser", False) or getattr(user, "is_staff", False) or getattr(user, "role", "") in ["ADMIN", "STAFF"])
        )
        if not is_admin_view:
            data.pop("admin_notes", None)
            data.pop("reviewed_by", None)
            data.pop("reviewed_by_email", None)
        return data


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
