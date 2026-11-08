"""Recorded data shaped for the charts on the web pages. Nothing new is collected here."""

from collections import defaultdict
from datetime import datetime, time, timedelta

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay
from django.utils import timezone

from .models import CameraPresence, ComputerActivity

SLOT_MINUTES = 15
KINDS = ('work', 'other', 'idle')


def day_bounds(day):
    start = timezone.make_aware(datetime.combine(day, time.min))
    return start, start + timedelta(days=1)


def kind_of(application, category):
    if application.casefold() == 'idle':
        return 'idle'
    return 'work' if category == ComputerActivity.Category.WORK else 'other'


def outside_schedule_seconds(employee, day, schedule=None):
    """Seconds at the computer (not idle) outside the working schedule, e.g. a student's classes."""
    from .schedule import Schedule

    schedule = schedule or Schedule.current()
    start, end = day_bounds(day)
    rows = (
        ComputerActivity.objects.filter(employee=employee, started_at__gte=start, started_at__lt=end)
        .exclude(application__iexact='idle')
        .values_list('started_at', 'duration_seconds')
    )
    return round(sum(duration - schedule.inside_seconds(started, duration) for started, duration in rows))


def time_split(employee, day):
    """Seconds in work programs, other programs and idle for one day."""
    start, end = day_bounds(day)
    rows = (
        ComputerActivity.objects.filter(employee=employee, started_at__gte=start, started_at__lt=end)
        .values('application', 'category')
        .annotate(seconds=Sum('duration_seconds'))
    )
    split = dict.fromkeys(KINDS, 0.0)
    for row in rows:
        split[kind_of(row['application'], row['category'])] += row['seconds']
    return {kind: round(seconds) for kind, seconds in split.items()}


def day_timeline(employee, day):
    """15-minute slots that hold any record, each with its seconds per kind (local time)."""
    start, end = day_bounds(day)
    slots = defaultdict(lambda: dict.fromkeys(KINDS, 0.0))
    rows = ComputerActivity.objects.filter(employee=employee, started_at__gte=start, started_at__lt=end).values_list(
        'started_at', 'duration_seconds', 'application', 'category'
    )
    midnight = timezone.localtime(start)
    for started, duration, application, category in rows.iterator():
        kind = kind_of(application, category)
        left = timezone.localtime(started)
        right = min(left + timedelta(seconds=duration), end)
        while left < right:  # A segment may cross a slot boundary.
            slot = int((left - midnight).total_seconds() // (SLOT_MINUTES * 60))
            piece = min(right, midnight + timedelta(minutes=(slot + 1) * SLOT_MINUTES))
            slots[slot][kind] += (piece - left).total_seconds()
            left = piece
    return [
        {
            'slot': slot,
            'start': f'{slot * SLOT_MINUTES // 60:02d}:{slot * SLOT_MINUTES % 60:02d}',
            **{kind: round(seconds) for kind, seconds in values.items()},
        }
        for slot, values in sorted(slots.items())
    ]


def presence_by_hour(employee, day):
    """Camera samples per local hour: how often a person was seen, and how often not."""
    start, end = day_bounds(day)
    rows = (
        CameraPresence.objects.filter(employee=employee, timestamp__gte=start, timestamp__lt=end)
        .annotate(hour=ExtractHour('timestamp'))
        .values('hour')
        # Not named «present»: that would shadow the field the filter reads.
        .annotate(seen=Count('pk', filter=Q(present=True)), unseen=Count('pk', filter=Q(present=False)))
        .order_by('hour')
    )
    return [{'hour': row['hour'], 'present': row['seen'], 'absent': row['unseen']} for row in rows]


def score_trend(employee, day, days=30):
    from scoring.models import ProductivityScore

    rows = ProductivityScore.objects.filter(
        employee=employee, date__gt=day - timedelta(days=days), date__lte=day
    ).order_by('date')
    return [
        {
            'date': row.date.isoformat(),
            'score': float(row.score),
            'task_completion': float(row.task_completion),
            'quality': float(row.quality),
            'deadline_completion': float(row.deadline_completion),
            'work_process': float(row.work_process),
        }
        for row in rows
    ]


def month_comparison(people, start, end):
    """Average daily score and recorded work per person and per department, plus a weekday×hour grid."""
    from scoring.models import ProductivityScore

    ids = [person.pk for person in people]
    scores = {
        row['employee']: row
        for row in ProductivityScore.objects.filter(employee__in=ids, date__gte=start.date(), date__lt=end.date())
        .values('employee')
        .annotate(average=Avg('score'), days=Count('pk'))
    }
    activity = ComputerActivity.objects.filter(employee__in=ids, started_at__gte=start, started_at__lt=end).exclude(
        application__iexact='idle'
    )
    work = {
        row['employee']: row['seconds'] for row in activity.values('employee').annotate(seconds=Sum('duration_seconds'))
    }
    employees = []
    departments = defaultdict(lambda: {'people': 0, 'scores': [], 'work_seconds': 0.0})
    for person in people:
        score = scores.get(person.pk)
        name = person.department.name if person.department else 'Хэлтэсгүй'
        row = {
            'employee': person.pk,
            'name': person.get_full_name() or person.username,
            'department': name,
            'average_score': round(float(score['average']), 1) if score else None,
            'scored_days': score['days'] if score else 0,
            'work_seconds': round(work.get(person.pk, 0)),
        }
        employees.append(row)
        group = departments[name]
        group['people'] += 1
        group['work_seconds'] += row['work_seconds']
        if row['average_score'] is not None:
            group['scores'].append(row['average_score'])
    heatmap = [[0] * 24 for _ in range(7)]
    for row in (
        activity.annotate(weekday=ExtractIsoWeekDay('started_at'), hour=ExtractHour('started_at'))
        .values('weekday', 'hour')
        .annotate(seconds=Sum('duration_seconds'))
    ):
        heatmap[row['weekday'] - 1][row['hour']] = round(row['seconds'])
    return {
        'employees': employees,
        'departments': [
            {
                'department': name,
                'people': group['people'],
                'average_score': round(sum(group['scores']) / len(group['scores']), 1) if group['scores'] else None,
                'work_seconds': round(group['work_seconds']),
            }
            for name, group in sorted(departments.items())
        ],
        'heatmap': heatmap,  # [Monday … Sunday][0 … 23 h], seconds of non-idle work.
    }
