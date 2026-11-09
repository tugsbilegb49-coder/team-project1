"""Business rules for daily productivity scores."""

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, time, timedelta
from django.db import transaction

from django.db.models import Avg
from django.utils import timezone

from activity.models import ActivityEvent, ComputerActivity
from activity.reporting import camera_totals_for_day
from activity.schedule import Schedule
from workforce.models import Task
from .models import ProductivityScore


ZERO = Decimal('0')
HUNDRED = Decimal('100')
TWO_PLACES = Decimal('0.01')


def _percentage(numerator, denominator) -> Decimal:
    if not denominator:
        return ZERO
    return (Decimal(str(numerator)) * HUNDRED / Decimal(str(denominator))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _clamp(value) -> Decimal:
    value = Decimal(str(value or 0))
    return max(ZERO, min(HUNDRED, value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def category_for(score: Decimal) -> str:
    if score >= Decimal('85'):
        return ProductivityScore.Category.HIGH
    if score >= Decimal('65'):
        return ProductivityScore.Category.MEDIUM
    return ProductivityScore.Category.LOW


def has_work_on(employee, score_date):
    """Anything to score: a task due that day, computer activity, or camera activity.

    Without any of these (a weekend, a day off, an admin who does not track time) a score would
    only be a misleading 0 that drags monthly averages down.
    """
    start = timezone.make_aware(datetime.combine(score_date, time.min))
    end = start + timedelta(days=1)
    return (
        Task.objects.filter(employee=employee, due_date=score_date).exists()
        or ComputerActivity.objects.filter(employee=employee, started_at__gte=start, started_at__lt=end).exists()
        or ActivityEvent.objects.filter(employee=employee, timestamp__gte=start, timestamp__lt=end).exists()
    )


class ScoreNotReady(ValueError):
    def __init__(self, message, task_ids):
        super().__init__(message)
        self.task_ids = task_ids


@transaction.atomic
def calculate_daily_score(employee, score_date):
    """Calculate and persist one employee's score for one day.

    T = completed tasks / tasks due that day
    Q = mean manager quality assessment for completed tasks
    D = tasks completed no later than their due date / tasks due that day
    W = productive foreground-app seconds / all desktop-agent seconds, counted within the
    working schedule (Тохиргоо → Ажлын хуваарь) so that, say, a student's class hours do not
    lower it; on a day with nothing inside the schedule the whole day counts. If the desktop
    agent has not supplied data for the day, camera WORKING seconds / all camera activity
    seconds is used as a fallback.
    """
    tasks = Task.objects.filter(employee=employee, due_date=score_date)
    task_count = tasks.count()
    missing_completion = list(
        tasks.filter(status=Task.Status.DONE, completed_at__isnull=True).values_list('pk', flat=True)
    )
    if missing_completion:
        raise ScoreNotReady('Completed tasks need a completion timestamp.', missing_completion)
    day_end = timezone.make_aware(datetime.combine(score_date + timedelta(days=1), time.min))
    completed = tasks.filter(status=Task.Status.DONE, completed_at__lt=day_end)
    missing_quality = list(completed.filter(quality_score__isnull=True).values_list('pk', flat=True))
    if missing_quality:
        raise ScoreNotReady(
            'Enter quality_score for every completed task before calculating this day.', missing_quality
        )
    completed_count = completed.count()
    on_time_count = sum(
        1
        for task in completed.exclude(completed_at__isnull=True)
        if timezone.localtime(task.completed_at).date() <= task.due_date
    )

    task_completion = _percentage(completed_count, task_count)
    quality = _clamp(completed.aggregate(value=Avg('quality_score'))['value'])
    deadline_completion = _percentage(on_time_count, task_count)

    segments = list(
        ComputerActivity.objects.filter(employee=employee, started_at__date=score_date).values_list(
            'started_at', 'duration_seconds', 'category'
        )
    )
    if segments:
        schedule = Schedule.current()
        inside = [(category, schedule.inside_seconds(start, duration)) for start, duration, category in segments]
        if not any(seconds for _, seconds in inside):  # Nothing inside the schedule: use the whole day.
            inside = [(category, duration) for _, duration, category in segments]
        work = ComputerActivity.Category.WORK
        work_process = _percentage(
            sum(seconds for category, seconds in inside if category == work), sum(seconds for _, seconds in inside)
        )
    else:
        state_totals = camera_totals_for_day(employee, score_date)
        all_activity_seconds = sum(state_totals.values())
        work_process = _percentage(state_totals.get(ActivityEvent.State.WORKING, 0), all_activity_seconds)

    score = _clamp(
        Decimal('0.4') * task_completion
        + Decimal('0.3') * quality
        + Decimal('0.2') * deadline_completion
        + Decimal('0.1') * work_process
    )
    score, _ = ProductivityScore.objects.update_or_create(
        employee=employee,
        date=score_date,
        defaults={
            'task_completion': task_completion,
            'quality': quality,
            'deadline_completion': deadline_completion,
            'work_process': work_process,
            'score': score,
            'category': category_for(score),
        },
    )
    return score
