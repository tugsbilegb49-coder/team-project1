from django.contrib import admin

from .models import (
    CameraAnalytics,
    ComputerActivity,
    ConsentRecord,
    Department,
    Employee,
    Task,
)

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "department", "created_at")
    search_fields = ("full_name", "email")
    list_filter = ("department",)


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ("employee", "consent_type", "is_granted", "granted_at")
    list_filter = ("consent_type", "is_granted")
    search_fields = ("employee__full_name", "employee__email")
    ordering = ("-id",)

    def has_delete_permission(self, request, obj=None):
        # Keep the decision history so removing a revocation cannot restore an old grant.
        return False


@admin.register(ComputerActivity)
class ComputerActivityAdmin(admin.ModelAdmin):
    list_display = ("employee", "date", "active_seconds", "idle_seconds", "app_name")
    list_filter = ("date", "app_name")
    search_fields = ("employee__full_name", "app_name")
    date_hierarchy = "date"


@admin.register(CameraAnalytics)
class CameraAnalyticsAdmin(admin.ModelAdmin):
    list_display = ("employee", "observed_at", "is_at_desk", "confidence")
    list_filter = ("is_at_desk", "observed_at")
    search_fields = ("employee__full_name",)
    date_hierarchy = "observed_at"


admin.site.register([Department, Task])
