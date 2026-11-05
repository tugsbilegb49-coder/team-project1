from rest_framework import serializers

from .models import ActivityEvent, ComputerActivity


class ActivityEventSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.username", read_only=True)

    class Meta:
        model = ActivityEvent
        fields = [
            "id", "employee", "employee_name", "timestamp", "state",
            "duration_seconds", "source_person_id", "imported_at",
        ]
        read_only_fields = ["id", "imported_at"]


class ActivityEventIngestSerializer(serializers.ModelSerializer):
    """The local camera may only write state data for its authenticated user."""

    class Meta:
        model = ActivityEvent
        fields = ["timestamp", "state", "duration_seconds", "device_id"]

    device_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)


class ComputerActivitySerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.username", read_only=True)

    class Meta:
        model = ComputerActivity
        fields = [
            "id", "employee", "employee_name", "started_at", "duration_seconds",
            "application", "category", "imported_at",
        ]
        read_only_fields = ["id", "imported_at"]


class ComputerActivityIngestSerializer(serializers.ModelSerializer):
    """The desktop agent must never choose the employee it writes for."""

    class Meta:
        model = ComputerActivity
        fields = ["started_at", "duration_seconds", "application", "category", "device_id"]

    device_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)

