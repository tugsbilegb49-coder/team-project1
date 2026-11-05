from rest_framework import serializers

from .models import ProductivityScore


class ProductivityScoreSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.username", read_only=True)

    class Meta:
        model = ProductivityScore
        fields = [
            "id", "employee", "employee_name", "date", "task_completion", "quality",
            "deadline_completion", "work_process", "score", "category", "calculated_at",
        ]
        read_only_fields = fields

