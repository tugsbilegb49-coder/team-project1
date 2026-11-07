"""Scoped operational status, audit, notifications, settings and report export."""
import csv
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
import math

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, F, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AgentHeartbeat, AuditEntry, Device, MonitoringSettings
from .permissions import IsSystemAdmin

User = get_user_model()
HEARTBEAT_SECONDS = 90
ERROR_CODES = ('', 'network', 'authentication', 'permission', 'storage', 'login_changed', 'invalid_event', 'legacy_queue')
SETTING_FIELDS = ('productive_apps', 'camera_threshold', 'presence_log_max_bytes', 'presence_log_backups',
                  'presence_log_retention_days', 'activity_retention_days', 'automatic_retention')


def visible_users(user):
    rows = User.objects.all()
    if user.is_admin_role: return rows
    if user.is_manager and user.department_id: return rows.filter(department_id=user.department_id)
    return rows.filter(pk=user.pk)


def scoped(rows, user, field='employee'):
    return rows.filter(**{field+'__in': visible_users(user)})


def audit_event(actor, resource, object_id, action, changes=None, employee=None):
    return AuditEntry.objects.create(actor=actor, actor_label=actor.username, employee=employee,
        resource=resource, object_id=str(object_id), action=action, changes=changes or {})


def snapshot(instance, fields):
    return {name: str(value) if isinstance(value := getattr(instance, name, None), (Decimal, date, datetime)) else value for name in fields}


def audit_update(actor, resource, instance, before, fields, employee=None, action='update'):
    after = snapshot(instance, fields)
    changes = {name: {'before': before.get(name), 'after': after[name]} for name in after if before.get(name) != after[name]}
    if changes or action != 'update':
        audit_event(actor, resource, instance.pk, action, changes, employee)


def current_settings():
    return MonitoringSettings.objects.get_or_create(pk=1)[0]


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        from collections.abc import Mapping
        if not isinstance(data, Mapping) or set(data) - set(self.fields):
            raise ValidationError({'detail': 'Only the documented fields are accepted.'})
        return super().to_internal_value(data)


class SettingsInput(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1)
    productive_apps = serializers.ListField(child=serializers.CharField(max_length=120), max_length=100, required=False)
    camera_threshold = serializers.FloatField(min_value=.05, max_value=1, required=False)
    presence_log_max_bytes = serializers.IntegerField(min_value=256, max_value=104857600, required=False)
    presence_log_backups = serializers.IntegerField(min_value=0, max_value=20, required=False)
    presence_log_retention_days = serializers.IntegerField(min_value=1, max_value=365, required=False)
    activity_retention_days = serializers.IntegerField(min_value=1, max_value=3650, required=False)
    automatic_retention = serializers.BooleanField(required=False)

    def validate_productive_apps(self, values):
        values = [value.strip() for value in values]
        if any(not value for value in values) or len({value.casefold() for value in values}) != len(values):
            raise ValidationError('App names must be non-empty and unique.')
        return values

    def validate_camera_threshold(self, value):
        if not math.isfinite(value): raise ValidationError('Use a finite confidence threshold.')
        return value


def settings_data(value):
    return {name: getattr(value, name) for name in (*SETTING_FIELDS, 'version', 'updated_at')}


class MonitoringSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(settings_data(current_settings()))

    @transaction.atomic
    def patch(self, request):
        if not request.user.is_admin_role: raise PermissionDenied('Only admins can change monitoring settings.')
        serializer = SettingsInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        expected = values.pop('expected_version')
        existing = current_settings()
        before = snapshot(existing, SETTING_FIELDS)
        updated = MonitoringSettings.objects.filter(pk=1, version=expected).update(**values,
            version=F('version')+1, updated_by=request.user, updated_at=timezone.now())
        if not updated: return Response({'detail': 'Settings changed. Reload before saving again.'}, status=409)
        existing.refresh_from_db()
        audit_update(request.user, 'monitoring_settings', existing, before, SETTING_FIELDS, action='configure')
        return Response(settings_data(existing))


class HeartbeatInput(StrictSerializer):
    device_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=('computer', 'camera', 'activity-agent'))
    queue_count = serializers.IntegerField(min_value=0, max_value=10000)
    paused = serializers.BooleanField()
    last_upload_at = serializers.DateTimeField(required=False, allow_null=True)
    error_code = serializers.ChoiceField(choices=ERROR_CODES, required=False, default='')
    agent_version = serializers.CharField(max_length=40, required=False, default='')
    settings_version = serializers.IntegerField(min_value=0, required=False, default=0)

    def validate_last_upload_at(self, value):
        if value and value > timezone.now(): raise ValidationError('Upload time cannot be in the future.')
        return value


def heartbeat_data(value):
    online = value.device.enabled and (timezone.now()-value.seen_at).total_seconds() <= HEARTBEAT_SECONDS
    return {'kind': value.kind, 'seen_at': value.seen_at, 'queue_count': value.queue_count,
        'paused': value.paused, 'last_upload_at': value.last_upload_at, 'error_code': value.error_code,
        'agent_version': value.agent_version, 'settings_version': value.settings_version,
        'online': online, 'state': 'disabled' if not value.device.enabled else 'offline' if not online else 'paused' if value.paused else 'online'}


class DeviceStatusSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.username', read_only=True)
    agents = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = ['id', 'employee', 'employee_name', 'name', 'platform', 'enabled', 'agents']

    def get_agents(self, value):
        return [heartbeat_data(row) for row in value.heartbeats.all()]


class AgentStatusViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DeviceStatusSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return scoped(Device.objects.select_related('employee').prefetch_related('heartbeats').order_by('name'), self.request.user)

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def heartbeat(self, request):
        serializer = HeartbeatInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        device = Device.objects.filter(pk=data.pop('device_id'), employee=request.user, enabled=True).first()
        if device is None: raise PermissionDenied('Device is not enabled for this account.')
        kind = data.pop('kind')
        # A restarted worker has no upload yet; retain the server's last known success.
        if data.get('last_upload_at') is None: data.pop('last_upload_at', None)
        record, _ = AgentHeartbeat.objects.update_or_create(device=device, kind=kind, defaults={**data, 'seen_at': timezone.now()})
        Device.objects.filter(pk=device.pk).update(last_seen_at=record.seen_at)
        return Response(heartbeat_data(record))


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEntry
        fields = ['id', 'actor', 'actor_label', 'employee', 'action', 'resource', 'object_id', 'changes', 'created_at']
        read_only_fields = fields


class AuditViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AuditSerializer

    def get_queryset(self):
        rows = AuditEntry.objects.all()
        if self.request.user.is_admin_role: return rows
        return scoped(rows, self.request.user)


class NotificationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from workforce.models import Task
        users = visible_users(request.user)
        today, now = timezone.localdate(), timezone.now()
        tasks = Task.objects.filter(employee__in=users, due_date__lte=today).exclude(status=Task.Status.DONE).order_by('due_date', 'id')
        alerts = [{'id': f'task-{task.pk}', 'kind': 'task_overdue' if task.due_date < today else 'task_due_today',
                   'message': task.title, 'employee_id': task.employee_id, 'due_date': task.due_date} for task in tasks[:100]]
        beats = AgentHeartbeat.objects.select_related('device').filter(device__employee__in=users, device__enabled=True)
        for beat in beats.order_by('-seen_at')[:100]:
            kind = 'agent_offline' if (now-beat.seen_at).total_seconds() > HEARTBEAT_SECONDS else 'upload_error' if beat.error_code else 'queue_pending' if beat.queue_count else None
            if kind:
                alerts.append({'id': f'agent-{beat.pk}-{kind}', 'kind': kind, 'message': beat.device.name,
                               'employee_id': beat.device.employee_id, 'queue_count': beat.queue_count, 'error_code': beat.error_code})
        return Response({'items': alerts, 'count': len(alerts), 'truncated': tasks.count() > 100 or beats.count() > 100})


def safe_cell(value):
    if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'"+value
    return value


class ReportExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from activity.models import ComputerActivity, CameraPresence
        from scoring.models import ProductivityScore
        try:
            first = date.fromisoformat(request.query_params.get('start', str(timezone.localdate())))
            last = date.fromisoformat(request.query_params.get('end', str(first)))
        except (TypeError, ValueError): raise ValidationError('Use ISO dates for start and end.')
        if not 0 <= (last-first).days < 366 or last > timezone.localdate():
            raise ValidationError('Use a past/current range of at most 366 days.')
        employees = visible_users(request.user).order_by('pk')
        employee_id = request.query_params.get('employee_id')
        if employee_id and employee_id != 'all':
            if not employee_id.isdecimal(): raise ValidationError('Use an employee ID.')
            employees = employees.filter(pk=employee_id)
            if not employees.exists(): raise PermissionDenied('Employee is outside your reporting scope.')
        employees = list(employees)
        days = (last-first).days+1
        if days * len(employees) > 50000: raise ValidationError('Export is too large. Select fewer employees or days.')
        begin = timezone.make_aware(datetime.combine(first, time.min))
        end = timezone.make_aware(datetime.combine(last+timedelta(days=1), time.min))
        scores = {(row.employee_id, row.date): row for row in ProductivityScore.objects.filter(employee__in=employees, date__range=(first,last))}
        from django.db.models.functions import TruncDate
        activity = {}
        for row in ComputerActivity.objects.filter(employee__in=employees, started_at__gte=begin, started_at__lt=end).annotate(day=TruncDate('started_at')).values('employee_id','day','category').annotate(seconds=Sum('duration_seconds')):
            values = activity.setdefault((row['employee_id'],row['day']), [0,0]);values[0] += row['seconds']
            if row['category']=='WORK': values[1] += row['seconds']
        presence = {}
        for row in CameraPresence.objects.filter(employee__in=employees, timestamp__gte=begin, timestamp__lt=end).annotate(day=TruncDate('timestamp')).values('employee_id','day','present').annotate(count=Count('pk')):
            values = presence.setdefault((row['employee_id'],row['day']), [0,0]);values[0] += row['count']
            if row['present']: values[1] += row['count']
        rows = [['date','employee_id','username','score','category','computer_seconds','work_seconds','presence_samples','present_samples']]
        for offset in range(days):
            day = first+timedelta(days=offset)
            for employee in employees:
                key=(employee.pk,day);score=scores.get(key)
                rows.append([str(day),employee.pk,safe_cell(employee.username),float(score.score) if score else None,
                             score.category if score else '',*activity.get(key,[0,0]),*presence.get(key,[0,0])])
        kind = request.query_params.get('file_type','csv')
        if kind == 'csv':
            buffer=StringIO(newline='');csv.writer(buffer,lineterminator='\n').writerows(rows)
            response=HttpResponse(buffer.getvalue().encode('utf-8-sig'),content_type='text/csv; charset=utf-8')
        elif kind == 'xlsx':
            from openpyxl import Workbook
            book=Workbook(write_only=True);sheet=book.create_sheet('Daily report')
            for row in rows: sheet.append(row)
            buffer=BytesIO();book.save(buffer)
            response=HttpResponse(buffer.getvalue(),content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        else: raise ValidationError('file_type must be csv or xlsx.')
        response['Content-Disposition']=f'attachment; filename="worktrack-{first}-{last}.{kind}"'
        audit_event(request.user,'report',f'{first}:{last}','export',{'file_type':kind,'rows':len(rows)-1},
                    employees[0] if len(employees)==1 else None)
        return response
