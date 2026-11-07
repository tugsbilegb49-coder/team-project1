"""Account-scoped monthly summaries and idempotent launcher interval ingestion."""
from collections import defaultdict
from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q, F, Min, Max
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from activity.models import ComputerActivity, ArchivedMonthlyActivity, ArchivedActivityReceipt
from activity.validation import lock_employee, activity_fingerprint
from workforce.models import Task, TaskWorkSession, TaskTransfer
from workforce.workflow import session_end
from .models import ConsentRecord, Device, LauncherInterval
from .operations import StrictSerializer, visible_users

ZONE = ZoneInfo('Asia/Ulaanbaatar')


def following(value):
    return value.replace(year=value.year+1, month=1) if value.month == 12 else value.replace(month=value.month+1)


def month_bounds(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}', value):
        raise ValidationError({'month': 'Use YYYY-MM.'})
    try:
        start = datetime.strptime(value, '%Y-%m').replace(tzinfo=ZONE)
        if start.year < 2000 or start.year > 2100:
            raise ValueError()
        return start, following(start)
    except ValueError as exc:
        raise ValidationError({'month': 'Use a valid month between 2000 and 2100.'}) from exc


def clipped_seconds(left, right, start, end):
    return max(0, (min(right, end)-max(left, start)).total_seconds())


def union_seconds(intervals, start, end):
    total, cursor = 0.0, start
    for left, right in sorted(intervals):
        left, right = max(left, cursor, start), min(right, end)
        if right > left:
            total += (right-left).total_seconds()
            cursor = right
    return total


class IntervalInput(StrictSerializer):
    event_id = serializers.UUIDField()
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField()

    def validate(self, data):
        duration = (data['ended_at']-data['started_at']).total_seconds()
        # Local records rotate hourly; accept a small checkpoint margin.
        if duration < 0 or duration > 3660 or data['ended_at'] > timezone.now()+timedelta(seconds=5):
            raise ValidationError('Invalid launcher interval duration or future time.')
        return data


class UsageInput(StrictSerializer):
    device_id = serializers.UUIDField()
    intervals = IntervalInput(many=True, max_length=100)


class LauncherUsageView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = UsageInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        lock_employee(request.user)
        consent = ConsentRecord.objects.filter(employee=request.user).first()
        if not consent or not consent.is_active:
            raise PermissionDenied('Active monitoring consent is required.')
        device = Device.objects.select_for_update().filter(pk=serializer.validated_data['device_id'], employee=request.user, enabled=True).first()
        if device is None:
            raise PermissionDenied('Device is not enabled for this account.')
        for item in serializer.validated_data['intervals']:
            if item['started_at'] < device.created_at-timedelta(seconds=5):
                raise ValidationError('Launcher time cannot predate device registration.')
            row, created = LauncherInterval.objects.get_or_create(employee=request.user, event_id=item['event_id'],
                defaults={'device': device, 'started_at': item['started_at'], 'ended_at': item['ended_at']})
            if not created:
                if row.device_id != device.pk or row.started_at != item['started_at']:
                    raise ValidationError('Interval identity cannot be changed.')
                if item['ended_at'] > row.ended_at:
                    row.ended_at = item['ended_at']
                    row.save(update_fields=['ended_at', 'received_at'])
        return Response({'accepted': len(serializer.validated_data['intervals'])})


def archive_activity(rows):
    """Called in the same transaction as locked raw-row deletion, exactly once."""
    totals = defaultdict(float)
    for row in rows:
        _, created = ArchivedActivityReceipt.objects.get_or_create(employee_id=row.employee_id, fingerprint=activity_fingerprint({
            'started_at': row.started_at, 'duration_seconds': row.duration_seconds, 'application': row.application}))
        if not created:
            continue
        left, end = row.started_at.astimezone(ZONE), row.started_at+timedelta(seconds=row.duration_seconds)
        while left < end:
            month = left.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            right = min(end, following(month))
            totals[(row.employee_id, month.date(), row.application)] += (right-left).total_seconds()
            left = right
    for (employee_id, month, application), seconds in totals.items():
        row, _ = ArchivedMonthlyActivity.objects.get_or_create(employee_id=employee_id, month=month, application=application)
        ArchivedMonthlyActivity.objects.filter(pk=row.pk).update(seconds=F('seconds')+seconds)


class MonthlyReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        month = request.query_params.get('month', now.astimezone(ZONE).strftime('%Y-%m'))
        start, end = month_bounds(month)
        people = list(visible_users(request.user).select_related('department').order_by('username'))
        ids = [person.pk for person in people]
        rows = {person.pk: {'employee': person.pk, 'username': person.username,
            'name': person.get_full_name() or person.username, 'department': person.department.name if person.department else '',
            'is_active': person.is_active, 'launcher_seconds': 0, 'launcher_recorded_since': None, 'launcher_last_upload': None,
            'application_seconds': 0, 'idle_seconds': 0, 'tracked_seconds': 0, 'task_seconds': 0,
            'completed_tasks': [], 'tasks': {}, 'transfers_sent': 0, 'transfers_received': 0, 'applications': defaultdict(float)} for person in people}
        intervals = defaultdict(list)
        usage = LauncherInterval.objects.filter(employee_id__in=ids)
        for item in usage.values('employee_id').annotate(first=Min('started_at'), last=Max('received_at')):
            rows[item['employee_id']].update(launcher_recorded_since=item['first'], launcher_last_upload=item['last'])
        for item in usage.filter(started_at__lt=end, ended_at__gt=start):
            intervals[item.employee_id].append((item.started_at, item.ended_at))
        for employee, segments in intervals.items():
            rows[employee]['launcher_seconds'] = union_seconds(segments, start, min(end, now))
        for item in ArchivedMonthlyActivity.objects.filter(employee_id__in=ids, month=start.date()):
            rows[item.employee_id]['applications'][item.application] += item.seconds
        # Historical imports may span a month boundary, so filter on END in Python.
        for item in ComputerActivity.objects.filter(employee_id__in=ids, started_at__lt=end).iterator():
            seconds = clipped_seconds(item.started_at, item.started_at+timedelta(seconds=item.duration_seconds), start, min(end, now))
            if seconds:
                rows[item.employee_id]['applications'][item.application] += seconds
        for item in TaskWorkSession.objects.filter(employee_id__in=ids, started_at__lt=end).filter(
                Q(ended_at__isnull=True) | Q(ended_at__gt=start)).select_related('contribution__task'):
            seconds = clipped_seconds(item.started_at, session_end(item, now), start, min(end, now))
            if not seconds:
                continue
            row, task = rows[item.employee_id], item.contribution.task
            row['task_seconds'] += seconds
            detail = row['tasks'].setdefault(task.pk, {'id': task.pk, 'title': task.title, 'status': task.status,
                'seconds': 0, 'contribution_percent': str(item.contribution.percent)})
            detail['seconds'] += seconds
        for task in Task.objects.filter(employee_id__in=ids, status=Task.Status.DONE, completed_at__gte=start, completed_at__lt=end):
            rows[task.employee_id]['completed_tasks'].append({'id': task.pk, 'title': task.title, 'completed_at': task.completed_at})
        for item in TaskTransfer.objects.filter(status=TaskTransfer.Status.ACCEPTED, responded_at__gte=start, responded_at__lt=end).filter(
                Q(from_employee_id__in=ids) | Q(to_employee_id__in=ids)):
            if item.from_employee_id in rows:
                rows[item.from_employee_id]['transfers_sent'] += 1
            if item.to_employee_id in rows:
                rows[item.to_employee_id]['transfers_received'] += 1
        for row in rows.values():
            row['idle_seconds'] = sum(value for app, value in row['applications'].items() if app.casefold() == 'idle')
            row['tracked_seconds'] = sum(row['applications'].values())
            row['application_seconds'] = row['tracked_seconds']-row['idle_seconds']
            row['applications'] = [{'application': app, 'seconds': value} for app, value in sorted(row['applications'].items(), key=lambda pair: -pair[1])]
            row['tasks'] = sorted(row['tasks'].values(), key=lambda item: -item['seconds'])
        return Response({'month': month, 'timezone': str(ZONE), 'generated_at': now, 'employees': list(rows.values())})
