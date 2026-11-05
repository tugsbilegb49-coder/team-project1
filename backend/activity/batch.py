"""Compatibility ingest for the activity_agent v1 batch contract."""
from datetime import timedelta
import hashlib
from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from users.models import Device
from .models import ComputerActivity
from .views import _require_consent


class AppSeconds(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    seconds = serializers.IntegerField(min_value=0)


class BatchSerializer(serializers.Serializer):
    schema_version = serializers.ChoiceField(choices=['1.0'])
    agent_version = serializers.CharField(max_length=40)
    employee_id = serializers.CharField()
    device_id = serializers.CharField(max_length=64)
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    active_seconds = serializers.IntegerField(min_value=0)
    idle_seconds = serializers.IntegerField(min_value=0)
    keyboard_events = serializers.IntegerField(min_value=0)
    mouse_events = serializers.IntegerField(min_value=0)
    apps = AppSeconds(many=True, max_length=500)

    def validate(self, data):
        duration = (data['period_end'] - data['period_start']).total_seconds()
        if duration <= 0 or duration > 3600:
            raise serializers.ValidationError('Batch length must be between 0 and 3600 seconds.')
        if data['active_seconds'] + data['idle_seconds'] > duration + 2:
            raise serializers.ValidationError('Activity exceeds the batch duration.')
        if sum(app['seconds'] for app in data['apps']) > data['active_seconds'] + 2:
            raise serializers.ValidationError('Application seconds exceed active time.')
        if any(key in self.initial_data for key in ['keys','text','keystrokes','password','clipboard','x','y','coordinates','window_title','file_content']):
            raise serializers.ValidationError('Private content fields are not accepted.')
        return data


class ActivityBatchView(APIView):
    def post(self, request):
        _require_consent(request)
        serializer = BatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data['employee_id'] not in {str(request.user.pk), request.user.username}:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('employee_id must match the authenticated user.')
        # Keep this legacy device namespace separate from enrolled UUID workstations.
        device_name = 'activity-agent-' + hashlib.sha256(data['device_id'].encode()).hexdigest()[:32]
        with transaction.atomic():
            device, _ = Device.objects.get_or_create(employee=request.user, name=device_name, defaults={'platform':'activity_agent'})
            if not device.enabled:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('This device is disabled.')
            cursor = data['period_start']
            created = 0
            # Alphabetical order provides deterministic replay keys. This contract
            # has aggregate app times; offsets do not represent observed app order.
            for app in sorted(data['apps'], key=lambda row: (row['name'], row['seconds'])):
                if not app['seconds']:
                    continue
                _, new = ComputerActivity.objects.get_or_create(employee=request.user, defaults={'device': device},
                    started_at=cursor, duration_seconds=app['seconds'], application=app['name'], category='OTHER')
                created += int(new)
                cursor += timedelta(seconds=app['seconds'])
        return Response({'created':created}, status=201 if created else 200)
