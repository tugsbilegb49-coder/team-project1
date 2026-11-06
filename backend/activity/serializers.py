from rest_framework import serializers
from django.db import transaction
from .validation import interval, lock_employee, reject_overlap

from .models import ActivityEvent, ComputerActivity


class SegmentValidationMixin:
    def validate(self, attrs):
        fields = ('started_at', 'duration_seconds') if self.Meta.model is ComputerActivity else ('timestamp', 'duration_seconds')
        data = {name: attrs.get(name, getattr(self.instance, name, None)) for name in fields}
        if all(value is not None for value in data.values()):
            interval(self.Meta.model, data)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        employee = validated_data['employee']
        lock_employee(employee)
        reject_overlap(self.Meta.model, employee, validated_data)
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        # Serialize against ingestion and other edits of this employee's stream.
        lock_employee(instance.employee)
        employee = validated_data.get('employee', instance.employee)
        if employee.pk != instance.employee_id:
            raise serializers.ValidationError({'employee': 'Activity ownership cannot be changed.'})
        data = {field.name: getattr(instance, field.name) for field in instance._meta.fields}
        data.update(validated_data)
        reject_overlap(self.Meta.model, employee, data, exclude_pk=instance.pk)
        return super().update(instance, validated_data)


class ActivityEventSerializer(SegmentValidationMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.username", read_only=True)

    class Meta:
        model = ActivityEvent
        fields = [
            "id", "employee", "employee_name", "timestamp", "state",
            "duration_seconds", "source_person_id", "imported_at",
        ]
        read_only_fields = ["id", "imported_at"]


class ActivityEventIngestSerializer(SegmentValidationMixin, serializers.ModelSerializer):
    """The local camera may only write state data for its authenticated user."""

    class Meta:
        model = ActivityEvent
        fields = ["timestamp", "state", "duration_seconds", "device_id"]

    device_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)


class ComputerActivitySerializer(SegmentValidationMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.username", read_only=True)

    class Meta:
        model = ComputerActivity
        fields = [
            "id", "employee", "employee_name", "started_at", "duration_seconds",
            "application", "category", "imported_at",
        ]
        read_only_fields = ["id", "imported_at"]


class ComputerActivityIngestSerializer(SegmentValidationMixin, serializers.ModelSerializer):
    """The desktop agent must never choose the employee it writes for."""

    class Meta:
        model = ComputerActivity
        fields = ["started_at", "duration_seconds", "application", "category", "device_id"]

    device_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)

