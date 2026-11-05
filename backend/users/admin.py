from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ConsentRecord, Department, Device, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Work profile", {"fields": ("role", "department")}),)
    list_display = ("username", "email", "role", "department", "is_staff", "is_active")
    list_filter = ("role", "department", "is_staff", "is_active")


admin.site.register(Department)
admin.site.register(ConsentRecord)
admin.site.register(Device)

