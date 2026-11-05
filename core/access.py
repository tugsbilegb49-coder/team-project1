from rest_framework.permissions import BasePermission
from .models import Employee

def is_admin(user):
    return bool(user and user.is_authenticated) and (user.is_superuser or user.role == 'admin')

def visible_employees(user):
    qs = Employee.objects.select_related('user', 'department')
    if not user or not user.is_authenticated:
        return qs.none()
    if is_admin(user):
        return qs
    profile = qs.filter(user=user).first()
    if not profile:
        return qs.none()
    return qs.filter(department=profile.department) if user.role == 'manager' else qs.filter(pk=profile.pk)

class AdminOnly(BasePermission):
    def has_permission(self, request, view):
        return is_admin(request.user)

class AdminWrite(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (request.method in ('GET', 'HEAD', 'OPTIONS') or is_admin(request.user))
