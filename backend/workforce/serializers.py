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
    collaboration = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            "id", "employee", "employee_name", "assigned_by", "assigned_by_name",
            "title", "description", "status", "due_date", "completed_at",
            "quality_score", "created_at", "updated_at",
            "transfer_count", "collaboration", "can_manage",
        ]
        read_only_fields = ["id", "assigned_by", "completed_at", "created_at", "updated_at", "transfer_count"]

    def get_collaboration(self, task):
        from .workflow import collaboration_data
        return collaboration_data(task)

    def get_can_manage(self, task):
        from .workflow import can_manage
        return bool(self.context.get('request') and can_manage(self.context['request'].user, task))


    def validate_employee(self, employee):
        if self.instance and employee.pk != self.instance.employee_id:
            raise serializers.ValidationError('Хариуцагч солихдоо шилжүүлэх хүсэлт илгээж, хүлээн авагчийн зөвшөөрлийг авна уу.')
        assigning = self.instance is None or employee.pk != self.instance.employee_id
        if assigning and not employee.is_active:
            raise serializers.ValidationError("Tasks can only be assigned to active users.")
        return employee
