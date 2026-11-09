"""The signed-in employee's own week: time per day and per task (Monday-Sunday, Ulaanbaatar)."""

from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from activity.models import ComputerActivity
from workforce.models import Task, TaskWorkSession
from workforce.workflow import session_end
from .monthly import ZONE, clipped_seconds


def week_start(value):
    """Monday of the week that contains `value` (YYYY-MM-DD), or of the current week."""
    if not value:
        day = datetime.now(ZONE).date()
    else:
        try:
            day = date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError({'start': 'Огноог YYYY-MM-DD хэлбэрээр оруулна уу.'}) from exc
        if not 2000 <= day.year <= 2100:
            raise ValidationError({'start': '2000-2100 оны хооронд огноо сонгоно уу.'})
    return day - timedelta(days=day.weekday())


class MyWeekView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        first = week_start(request.query_params.get('start'))
        bounds = [datetime.combine(first + timedelta(days=i), time.min, tzinfo=ZONE) for i in range(8)]
        start, end, now = bounds[0], bounds[-1], timezone.now()
        days = [
            {
                'date': str(first + timedelta(days=i)),
                'task_seconds': 0.0,
                'application_seconds': 0.0,
                'idle_seconds': 0.0,
            }
            for i in range(7)
        ]

        def per_day(left, right):
            # Never count the future, and split intervals that cross midnight.
            return [clipped_seconds(left, right, bounds[i], min(bounds[i + 1], now)) for i in range(7)]

        # Agent segments are split at midnight, so one day of look-back catches every overlap.
        activity = ComputerActivity.objects.filter(
            employee=request.user, started_at__lt=end, started_at__gte=start - timedelta(days=1)
        )
        for item in activity.iterator():
            field = 'idle_seconds' if item.application.casefold() == 'idle' else 'application_seconds'
            for day, seconds in zip(
                days, per_day(item.started_at, item.started_at + timedelta(seconds=item.duration_seconds))
            ):
                day[field] += seconds

        tasks = {}
        sessions = (
            TaskWorkSession.objects.filter(employee=request.user, started_at__lt=end)
            .filter(Q(ended_at__isnull=True) | Q(ended_at__gt=start))
            .select_related('contribution__task')
        )
        for item in sessions:
            split = per_day(item.started_at, session_end(item, now))
            if not any(split):
                continue
            for day, seconds in zip(days, split):
                day['task_seconds'] += seconds
            task = item.contribution.task
            row = tasks.setdefault(task.pk, {'id': task.pk, 'title': task.title, 'status': task.status, 'seconds': 0.0})
            row['seconds'] += sum(split)

        for day in days:
            for field in ('task_seconds', 'application_seconds', 'idle_seconds'):
                day[field] = round(day[field])
        for row in tasks.values():
            row['seconds'] = round(row['seconds'])
        return Response(
            {
                'start': str(first),
                'end': str(first + timedelta(days=6)),
                'days': days,
                'totals': {
                    field: sum(day[field] for day in days)
                    for field in ('task_seconds', 'application_seconds', 'idle_seconds')
                },
                'tasks': sorted(tasks.values(), key=lambda row: (-row['seconds'], row['title']))[:10],
                'completed_tasks': Task.objects.filter(
                    employee=request.user, status=Task.Status.DONE, completed_at__gte=start, completed_at__lt=end
                ).count(),
            }
        )
