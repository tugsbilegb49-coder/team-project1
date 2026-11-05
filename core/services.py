from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.db.models import Avg, Sum, F
from .models import Task, ComputerActivity, ProductivityScore, Employee

def normalized(value):
    return min(Decimal('100'), max(Decimal('0'), Decimal(str(value)))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

def weighted_score(t, q, d, w):
    p = normalized(Decimal(str(t))*Decimal('.4') + Decimal(str(q))*Decimal('.3') + Decimal(str(d))*Decimal('.2') + Decimal(str(w))*Decimal('.1'))
    return p, 'High' if p >= 85 else 'Medium' if p >= 65 else 'Low'

@transaction.atomic
def calculate_score(employee, date):
    Employee.objects.select_for_update().get(pk=employee.pk)
    tasks = Task.objects.filter(employee=employee, due_at__date=date)
    total = tasks.count()
    completed = tasks.filter(status='done', completed_at__date__lte=date)
    done = completed.count()
    if completed.filter(quality_score__isnull=True).exists():
        from rest_framework.exceptions import ValidationError
        raise ValidationError('Quality review is required for all completed tasks before scoring.')
    t = normalized(100 * done / total if total else 0)
    q = normalized(completed.aggregate(value=Avg('quality_score'))['value'] or 0)
    on_time = completed.filter(completed_at__lte=F('due_at')).count()
    d = normalized(100 * on_time / total if total else 0)
    seconds = ComputerActivity.objects.filter(employee=employee, started_at__date=date).aggregate(value=Sum('active_seconds'))['value'] or 0
    w = normalized(Decimal(seconds) * 100 / (employee.expected_daily_minutes * 60))
    p, level = weighted_score(t, q, d, w)
    score, _ = ProductivityScore.objects.update_or_create(employee=employee, date=date,
        defaults={'t': t, 'q': q, 'd': d, 'w': w, 'p': p, 'level': level})
    return score
