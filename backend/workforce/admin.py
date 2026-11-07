from django.contrib import admin

from .models import Task
from users.audit_admin import AuditedAdminMixin


@admin.register(Task)
class TaskAdmin(AuditedAdminMixin, admin.ModelAdmin):
    audit_resource = 'task'
    audit_fields = ('employee_id','title','status','due_date','quality_score','completed_at')
    list_display = ("title", "employee", "status", "due_date", "quality_score")
    list_filter = ("status", "due_date")
    search_fields = ("title", "employee__username")

