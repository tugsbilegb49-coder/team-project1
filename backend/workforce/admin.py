from django.contrib import admin
from django.db import transaction

from .models import Task
from users.audit_admin import AuditedAdminMixin


@admin.register(Task)
class TaskAdmin(AuditedAdminMixin, admin.ModelAdmin):
    audit_resource = 'task'
    audit_fields = ('employee_id','title','status','due_date','quality_score','completed_at')
    list_display = ("title", "employee", "status", "due_date", "quality_score")
    list_filter = ("status", "due_date")
    search_fields = ("title", "employee__username")

    def get_readonly_fields(self, request, obj=None):
        return ('employee', 'transfer_count') if obj else ('transfer_count',)

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if change:
            current = Task.objects.select_for_update().get(pk=obj.pk)
            obj.employee_id, obj.transfer_count = current.employee_id, current.transfer_count
        super().save_model(request, obj, form, change)
        if obj.status == Task.Status.DONE:
            from .workflow import close_task
            close_task(obj)

