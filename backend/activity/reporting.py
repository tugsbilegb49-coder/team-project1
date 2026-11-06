"""Apportion camera intervals by the reporting day, not their end date."""
from collections import defaultdict
from datetime import datetime, time, timedelta
from django.utils import timezone
from .models import ActivityEvent


def camera_totals_for_day(employee, day):
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
    totals = defaultdict(float)
    for timestamp, duration, state in ActivityEvent.objects.filter(
            employee=employee, timestamp__gt=start).values_list('timestamp', 'duration_seconds', 'state').iterator():
        beginning = timestamp - timedelta(seconds=duration)
        seconds = (min(end, timestamp) - max(start, beginning)).total_seconds()
        if seconds > 0:
            totals[state] += seconds
    return dict(totals)
