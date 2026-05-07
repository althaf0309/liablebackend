from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db import transaction

from .models import User, LoginAudit, VisitorHit, VerificationStatus
from .email_utils import email_account_approved

@admin.action(description="✅ Approve selected users (activate + set temp password + send email)")
def approve_users(modeladmin, request, queryset):
    for user in queryset:
        if user.verification_status == VerificationStatus.APPROVED:
            continue

        temp_password = User.generate_temp_password()

        with transaction.atomic():
            user.set_password(temp_password)
            user.is_active = True
            user.verification_status = VerificationStatus.APPROVED
            user.verified_at = timezone.now()
            user.save()

            # ✅ If email fails -> rollback to pending
            try:
                email_account_approved(
                    to_email=user.email,
                    name=user.full_name or user.email,
                    login_email=user.email,
                    temp_password=temp_password,
                )
            except Exception as e:
                user.is_active = False
                user.verification_status = VerificationStatus.PENDING
                user.verified_at = None
                user.save(update_fields=["is_active", "verification_status", "verified_at"])
                raise e

@admin.action(description="❌ Reject selected users (disable)")
def reject_users(modeladmin, request, queryset):
    queryset.update(
        is_active=False,
        verification_status=VerificationStatus.REJECTED,
        verified_at=None,
    )

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("-created_at",)
    list_display = (
        "email", "full_name", "role",
        "verification_status", "is_active", "is_staff",
        "created_at", "verified_at",
        "last_login_at", "last_login_ip",
    )
    list_filter = ("role", "verification_status", "is_active", "is_staff", "is_superuser", "created_at")
    search_fields = ("email", "full_name", "phone")
    readonly_fields = ("id", "created_at", "last_login_at", "last_login_ip", "last_login", "verified_at")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Profile"), {"fields": ("full_name", "phone", "role")}),
        (_("Verification"), {"fields": ("verification_status", "verified_at")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Audit"), {"fields": ("created_by", "created_at", "last_login_at", "last_login_ip")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "full_name", "phone", "role", "password1", "password2", "is_active", "is_staff"),
        }),
    )

    actions = [approve_users, reject_users]
    username_field = "email"

@admin.register(LoginAudit)
class LoginAuditAdmin(admin.ModelAdmin):
    list_display = ("created_at", "success", "email_attempted", "user", "ip_address")
    list_filter = ("success", "created_at")
    search_fields = ("email_attempted", "user__email", "ip_address", "failure_reason")
    readonly_fields = ("user", "email_attempted", "success", "failure_reason", "ip_address", "user_agent", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

@admin.register(VisitorHit)
class VisitorHitAdmin(admin.ModelAdmin):
    list_display = ("created_at", "ip_address", "path", "referrer")
    list_filter = ("created_at",)
    search_fields = ("ip_address", "path", "referrer", "user_agent")
    readonly_fields = ("ip_address", "user_agent", "path", "referrer", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
