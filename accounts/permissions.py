from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import UserRole


class IsAdminOrStaff(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_superuser
                or user.is_staff
                or user.role in [UserRole.ADMIN, UserRole.STAFF]
            )
        )


class IsAdminOnly(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_superuser
                or user.role == UserRole.ADMIN
            )
        )


class IsAdminOrStaffReadOnlyOrAdminWrite(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.role == UserRole.ADMIN:
            return True
        if request.method in SAFE_METHODS:
            return bool(user.is_staff or user.role == UserRole.STAFF)
        return False
