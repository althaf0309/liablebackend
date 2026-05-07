from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import (
    User, LandlordProfile, StudentProfile,
    Question, Answer,
    VerificationStatus
)

class UserSerializer(serializers.ModelSerializer):
    landlord_profile = serializers.SerializerMethodField()
    student_profile = serializers.SerializerMethodField()
    form_details = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "phone",
            "role",
            "verification_status",
            "created_at",
            "verified_at",
            "landlord_profile",
            "student_profile",
            "form_details",
        ]
        read_only_fields = ["id", "created_at", "verified_at"]

    def get_landlord_profile(self, obj):
        if obj.role != "LANDLORD":
            return None
        profile = getattr(obj, "landlord_profile", None)
        if not profile:
            return None
        return LandlordProfileSerializer(profile).data

    def get_student_profile(self, obj):
        if obj.role != "STUDENT":
            return None
        profile = getattr(obj, "student_profile", None)
        if not profile:
            return None
        return StudentProfileSerializer(profile).data

    def get_form_details(self, obj):
        if obj.role == "LANDLORD":
            profile = getattr(obj, "landlord_profile", None)
            if not profile:
                return None
            return {
                "role": "LANDLORD",
                "details": LandlordProfileSerializer(profile).data,
            }

        if obj.role == "STUDENT":
            profile = getattr(obj, "student_profile", None)
            if not profile:
                return None
            return {
                "role": "STUDENT",
                "details": StudentProfileSerializer(profile).data,
            }

        return None

class LandlordProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = LandlordProfile
        fields = [
            "id", "property_address", "property_type", "number_of_properties",
            "bedrooms", "current_status", "expected_rent",
            "services_required", "additional_info", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

class StudentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentProfile
        fields = [
            "id", "nationality", "university", "course",
            "arrival_date", "accommodation_type",
            "budget", "services_needed", "additional_info", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

class LandlordRegisterSerializer(serializers.Serializer):
    fullName = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)

    propertyAddress = serializers.CharField(max_length=300)
    propertyType = serializers.CharField(max_length=80, allow_blank=True, required=False)
    numberOfProperties = serializers.CharField(max_length=50, allow_blank=True, required=False)
    bedrooms = serializers.CharField(max_length=20, allow_blank=True, required=False)
    currentStatus = serializers.CharField(max_length=80, allow_blank=True, required=False)
    expectedRent = serializers.CharField(max_length=40, allow_blank=True, required=False)
    servicesRequired = serializers.CharField(max_length=80, allow_blank=True, required=False)
    additionalInfo = serializers.CharField(allow_blank=True, required=False)

class StudentRegisterSerializer(serializers.Serializer):
    fullName = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)

    nationality = serializers.CharField(max_length=120)
    university = serializers.CharField(max_length=200, allow_blank=True, required=False)
    course = serializers.CharField(max_length=200, allow_blank=True, required=False)
    arrivalDate = serializers.DateField(required=False, allow_null=True)

    accommodationType = serializers.CharField(max_length=80, allow_blank=True, required=False)
    budget = serializers.CharField(max_length=80, allow_blank=True, required=False)
    servicesNeeded = serializers.CharField(max_length=120, allow_blank=True, required=False)
    additionalInfo = serializers.CharField(allow_blank=True, required=False)

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ["id", "target_role", "question_text", "is_required", "is_active", "sort_order"]

class AnswerUpsertSerializer(serializers.Serializer):
    answers = serializers.ListField(child=serializers.DictField(), allow_empty=False)

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, attrs):
        email = attrs.get("email").strip().lower()
        password = attrs.get("password")

        user = authenticate(email=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid credentials")

        if user.verification_status != VerificationStatus.APPROVED:
            raise serializers.ValidationError("Account not verified yet. Wait for admin approval.")

        if not user.is_active:
            raise serializers.ValidationError("Account disabled. Wait for admin approval.")

        attrs["user"] = user
        return attrs

class ForgotPasswordOTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

class ForgotPasswordOTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)
    new_password = serializers.CharField(min_length=8)

    def validate_new_password(self, value):
        validate_password(value)
        return value
