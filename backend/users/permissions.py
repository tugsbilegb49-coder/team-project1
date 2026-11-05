from rest_framework.permissions import BasePermission


class IsAdminOrManager(BasePermission):
    message = "Admin or manager access is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_admin_role or user.is_manager))


class IsSystemAdmin(BasePermission):
    """Allows the API's ADMIN role as well as a Django superuser."""

    message = "Admin access is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_admin_role)

