from rest_framework import serializers

from .models import Task
from users.models import Department


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "description"]
        read_only_fields = ["id"]


class TaskSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.username", read_only=True)
    assigned_by_name = serializers.CharField(source="assigned_by.username", read_only=True)

    class Meta:
        model = Task
        fields = [
            "id", "employee", "employee_name", "assigned_by", "assigned_by_name",
            "title", "description", "status", "due_date", "completed_at",
            "quality_score", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "assigned_by", "completed_at", "created_at", "updated_at"]

