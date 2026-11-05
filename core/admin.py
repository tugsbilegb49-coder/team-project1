from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Department, Employee, Task, Workstation, ConsentRecord, ComputerActivity, CameraObservation, ProductivityScore

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('API role', {'fields': ('role',)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('API role', {'fields': ('role',)}),)

for model in [Department, Employee, Task, Workstation]:
    admin.site.register(model)

class AuditAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

for model in [ConsentRecord, ComputerActivity, CameraObservation, ProductivityScore]:
    admin.site.register(model, AuditAdmin)
