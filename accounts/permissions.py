from rest_framework.permissions import BasePermission

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
