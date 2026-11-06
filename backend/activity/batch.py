"""Compatibility ingest for the activity_agent v1 batch contract."""
from datetime import timedelta
import hashlib
from django.db import transaction
from django.utils import timezone
from .validation import save_segment, lock_employee
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from users.models import Device
from .models import ComputerActivity
from .classification import category_for_application
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
        if data['period_end'] > timezone.now():
            raise serializers.ValidationError('Batch cannot finish in the future.')
        if sum(app['seconds'] for app in data['apps']) > duration:
            raise serializers.ValidationError('Application seconds exceed the period.')
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
            lock_employee(request.user)
            device, _ = Device.objects.get_or_create(employee=request.user, name=device_name, defaults={'platform':'activity_agent'})
            if not device.enabled:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('This device is disabled.')
            cursor = data['period_start']
            created = 0
            # Alphabetical order provides deterministic replay keys. This contract
            # has aggregate app times; offsets do not represent observed app order.
            def store(application, seconds, category):
                nonlocal cursor, created
                if seconds <= 0:
                    return
                identity = {'started_at':cursor, 'duration_seconds':seconds, 'application':application}
                # Classification settings can change after an accepted batch.
                # Replay preserves its original category rather than duplicating it.
                existing = ComputerActivity.objects.filter(employee=request.user, **identity).first()
                if existing is None:
                    _, new = save_segment(ComputerActivity, request.user, {**identity, 'category':category}, device)
                    created += int(new)
                cursor += timedelta(seconds=seconds)

            app_seconds = 0
            for app in sorted(data['apps'], key=lambda row: (row['name'], row['seconds'])):
                store(app['name'], app['seconds'], category_for_application(app['name']))
                app_seconds += app['seconds']
            # Preserve denominator time even when app resolution failed. Counts
            # and input contents are not stored; only duration and category are.
            remaining = max(0, (data['period_end'] - cursor).total_seconds())
            unknown = min(max(0, data['active_seconds'] - app_seconds), remaining)
            store('Unattributed activity', unknown, 'OTHER')
            remaining = max(0, (data['period_end'] - cursor).total_seconds())
            store('Idle', min(data['idle_seconds'], remaining), 'OTHER')
        return Response({'created':created}, status=201 if created else 200)
