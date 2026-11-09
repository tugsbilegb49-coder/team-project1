from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError
from django.db import models, transaction

from .audit import audit_value, write_audit
from .models import AuditLog, ConsentRecord, Department, Device, User


def protect_last_admin(request, obj, *, deleting=False, replacement=None):
    was_admin = obj.is_active and obj.is_admin_role
    next_user = replacement or obj
    remains_admin = next_user.is_active and (next_user.is_superuser or next_user.role == User.Role.ADMIN)
    if was_admin and (deleting or not obj.is_active or not remains_admin):
        others = User.objects.filter(is_active=True).exclude(pk=obj.pk).filter(
            models.Q(role=User.Role.ADMIN) | models.Q(is_superuser=True)
        )
        if not others.exists():
            raise ValidationError("The last active administrator cannot be removed or demoted.")
    if deleting and request.user.pk == obj.pk:
        raise ValidationError("You cannot delete your own account.")


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Work profile", {"fields": ("role", "department")}),)
    list_display = ("username", "email", "role", "department", "is_staff", "is_active")
    list_filter = ("role", "department", "is_staff", "is_active")

    def save_model(self, request, obj, form, change):
        fields = ("username", "email", "first_name", "last_name", "role", "department_id", "is_active", "is_staff", "is_superuser")
        before = None
        if change:
            old = User.objects.get(pk=obj.pk)
            before = {field: audit_value(getattr(old, field, None)) for field in fields}
            protect_last_admin(request, old, replacement=obj)
        super().save_model(request, obj, form, change)
        write_audit(request, entity_type="user", instance=obj, action="update" if change else "create",
                    before=before, fields=fields)

    def delete_model(self, request, obj):
        protect_last_admin(request, obj, deleting=True)
        write_audit(request, entity_type="user", instance=obj, action="delete",
                    fields=("username", "email", "role", "department_id", "is_active"))
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            active_admins = User.objects.filter(is_active=True).filter(
                models.Q(role=User.Role.ADMIN) | models.Q(is_superuser=True)
            ).count()
            selected_admins = queryset.filter(is_active=True).filter(
                models.Q(role=User.Role.ADMIN) | models.Q(is_superuser=True)
            ).count()
            if active_admins <= selected_admins:
                raise ValidationError("At least one active administrator must remain.")
            for obj in queryset.select_for_update():
                protect_last_admin(request, obj, deleting=True)
                write_audit(request, entity_type="user", instance=obj, action="delete",
                            fields=("username", "email", "role", "department_id", "is_active"))
                obj.delete()


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)

    def save_model(self, request, obj, form, change):
        before = None
        if change:
            old = Department.objects.get(pk=obj.pk)
            before = {"name": old.name, "description": old.description}
        super().save_model(request, obj, form, change)
        write_audit(request, entity_type="department", instance=obj, action="update" if change else "create",
                    before=before, fields=("name", "description"))

    def delete_model(self, request, obj):
        write_audit(request, entity_type="department", instance=obj, action="delete",
                    fields=("name", "description"))
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            for obj in queryset.select_for_update():
                write_audit(request, entity_type="department", instance=obj, action="delete",
                            fields=("name", "description"))
                obj.delete()


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor_label", "action", "entity_type", "target_label")
    list_filter = ("action", "entity_type", "created_at")
    search_fields = ("actor_label", "target_label", "entity_id")
    readonly_fields = tuple(field.name for field in AuditLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ("employee", "granted", "policy_version", "recorded_at", "revoked_at")
    readonly_fields = tuple(field.name for field in ConsentRecord._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Device)

