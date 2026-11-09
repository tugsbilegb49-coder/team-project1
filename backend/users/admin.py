from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError
from django.db import models, transaction

from .models import ConsentRecord, Department, Device, User, AuditEntry
from .audit_admin import AuditedAdminMixin


@admin.register(User)
class CustomUserAdmin(AuditedAdminMixin, UserAdmin):
    audit_resource = 'user'
    audit_fields = ('username', 'first_name', 'last_name', 'email', 'role', 'department_id', 'is_active', 'is_staff', 'is_superuser')
    fieldsets = UserAdmin.fieldsets + (('Work profile', {'fields': ('role', 'department')}),)
    list_display = ('username', 'email', 'role', 'department', 'is_staff', 'is_active')
    list_filter = ('role', 'department', 'is_staff', 'is_active')

    def _check_admin_remains(self, request, obj, *, replacement=None, deleting=False):
        if deleting and request.user.pk == obj.pk:
            raise ValidationError('You cannot delete your own account.')
        next_user = replacement or obj
        if obj.is_active and obj.is_admin_role and (
            deleting or not next_user.is_active or not (next_user.is_superuser or next_user.role == User.Role.ADMIN)
        ):
            others = User.objects.filter(is_active=True).exclude(pk=obj.pk).filter(
                models.Q(role=User.Role.ADMIN) | models.Q(is_superuser=True)
            )
            if not others.exists():
                raise ValidationError('The last active administrator cannot be removed or demoted.')

    def save_model(self, request, obj, form, change):
        if change:
            old = User.objects.get(pk=obj.pk)
            self._check_admin_remains(request, old, replacement=obj)
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        self._check_admin_remains(request, obj, deleting=True)
        super().delete_model(request, obj)

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        admins = User.objects.filter(is_active=True).filter(
            models.Q(role=User.Role.ADMIN) | models.Q(is_superuser=True)
        )
        if admins.count() <= queryset.filter(pk__in=admins.values('pk')).count():
            raise ValidationError('At least one active administrator must remain.')
        if queryset.filter(pk=request.user.pk).exists():
            raise ValidationError('You cannot delete your own account.')
        super().delete_queryset(request, queryset)


@admin.register(Department)
class DepartmentAdmin(AuditedAdminMixin, admin.ModelAdmin):
    audit_resource = 'department'
    audit_fields = ('name', 'description')


@admin.register(ConsentRecord)
class ConsentAdmin(AuditedAdminMixin, admin.ModelAdmin):
    audit_resource = 'consent'
    audit_fields = ('granted', 'policy_version', 'revoked_at')


@admin.register(Device)
class DeviceAdmin(AuditedAdminMixin, admin.ModelAdmin):
    audit_resource = 'device'
    audit_fields = ('name', 'platform', 'enabled')


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor_label', 'resource', 'object_id', 'action')
    readonly_fields = tuple(field.name for field in AuditEntry._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        from .operations import scoped

        rows = super().get_queryset(request)
        return rows if request.user.is_admin_role else scoped(rows, request.user)
