"""Business rules for daily productivity scores."""

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Avg, Sum

from activity.models import ActivityEvent, ComputerActivity
from workforce.models import Task
from .models import ProductivityScore


ZERO = Decimal("0")
HUNDRED = Decimal("100")
TWO_PLACES = Decimal("0.01")


def _percentage(numerator, denominator) -> Decimal:
    if not denominator:
        return ZERO
    return (Decimal(str(numerator)) * HUNDRED / Decimal(str(denominator))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _clamp(value) -> Decimal:
    value = Decimal(str(value or 0))
    return max(ZERO, min(HUNDRED, value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def category_for(score: Decimal) -> str:
    if score >= Decimal("85"):
        return ProductivityScore.Category.HIGH
    if score >= Decimal("65"):
        return ProductivityScore.Category.MEDIUM
    return ProductivityScore.Category.LOW


def calculate_daily_score(employee, score_date):
    """Calculate and persist one employee's score for one day.

    T = completed tasks / tasks due that day
    Q = mean manager quality assessment for completed tasks
    D = tasks completed no later than their due date / tasks due that day
    W = productive foreground-app seconds / all desktop-agent seconds. If the
    desktop agent has not supplied data for the day, camera WORKING seconds /
    all camera activity seconds is used as a fallback.
    """
    tasks = Task.objects.filter(employee=employee, due_date=score_date)
    task_count = tasks.count()
    completed = tasks.filter(status=Task.Status.DONE)
    completed_count = completed.count()
    on_time_count = sum(
        1
        for task in completed.exclude(completed_at__isnull=True)
        if task.completed_at.date() <= task.due_date
    )

    task_completion = _percentage(completed_count, task_count)
    quality = _clamp(completed.aggregate(value=Avg("quality_score"))["value"])
    deadline_completion = _percentage(on_time_count, task_count)

    computer_totals = ComputerActivity.objects.filter(employee=employee, started_at__date=score_date)
    computer_seconds = computer_totals.aggregate(value=Sum("duration_seconds"))["value"] or 0
    if computer_seconds:
        productive_seconds = (
            computer_totals.filter(category=ComputerActivity.Category.WORK)
            .aggregate(value=Sum("duration_seconds"))["value"]
            or 0
        )
        work_process = _percentage(productive_seconds, computer_seconds)
    else:
        state_totals = {
            row["state"]: row["seconds"] or 0
            for row in ActivityEvent.objects.filter(employee=employee, timestamp__date=score_date)
            .values("state")
            .annotate(seconds=Sum("duration_seconds"))
        }
        all_activity_seconds = sum(state_totals.values())
        work_process = _percentage(state_totals.get(ActivityEvent.State.WORKING, 0), all_activity_seconds)

    score = _clamp(
        Decimal("0.4") * task_completion
        + Decimal("0.3") * quality
        + Decimal("0.2") * deadline_completion
        + Decimal("0.1") * work_process
    )
    score, _ = ProductivityScore.objects.update_or_create(
        employee=employee,
        date=score_date,
        defaults={
            "task_completion": task_completion,
            "quality": quality,
            "deadline_completion": deadline_completion,
            "work_process": work_process,
            "score": score,
            "category": category_for(score),
        },
    )
    return score

