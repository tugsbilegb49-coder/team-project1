from django.contrib import admin

from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "employee", "status", "due_date", "quality_score")
    list_filter = ("status", "due_date")
    search_fields = ("title", "employee__username")

