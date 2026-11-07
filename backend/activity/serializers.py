from rest_framework import serializers
from django.db import transaction
from .validation import interval, lock_employee, reject_overlap, is_archived

from .models import ActivityEvent, ComputerActivity, CameraPresence


class CameraPresenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CameraPresence
        fields = ['id', 'employee', 'device', 'timestamp', 'present', 'confidence']
        read_only_fields = fields


class CameraPresenceIngestSerializer(serializers.Serializer):
    timestamp = serializers.DateTimeField()
    present = serializers.BooleanField()
    confidence = serializers.FloatField(min_value=0, max_value=1)
    device_id = serializers.UUIDField(required=False, allow_null=True)

    def to_internal_value(self, data):
        from collections.abc import Mapping
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({'non_field_errors': ['Expected a JSON object.']})
        extra = set(data) - set(self.fields)
        if extra:
            raise serializers.ValidationError({'non_field_errors': ['Only timestamp, present, confidence and device_id are accepted.']})
        if not isinstance(data.get('present'), bool):
            raise serializers.ValidationError({'present': 'Use a JSON boolean.'})
        if isinstance(data.get('confidence'), bool):
            raise serializers.ValidationError({'confidence': 'Use a finite number.'})
        return super().to_internal_value(data)

    def validate_confidence(self, value):
        import math
        if not math.isfinite(value):
            raise serializers.ValidationError('Use a finite confidence between 0 and 1.')
        return value

    def validate_timestamp(self, value):
        from django.utils import timezone
        if value > timezone.now():
            raise serializers.ValidationError('Presence cannot be in the future.')
        return value


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
        if self.Meta.model is ComputerActivity and is_archived(employee, validated_data):
            raise serializers.ValidationError('This segment has already been included in an archived monthly total.')
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
        if self.Meta.model is ComputerActivity and is_archived(employee, data):
            raise serializers.ValidationError('This segment has already been included in an archived monthly total.')
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

