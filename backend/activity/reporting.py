"""Apportion camera intervals by the reporting day, not their end date."""
from collections import defaultdict
from datetime import datetime, time, timedelta
from django.utils import timezone
from django.db.models import Count, Q
from .models import ActivityEvent, CameraPresence


def presence_summary_for_day(employee, day):
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
    rows = CameraPresence.objects.filter(employee=employee, timestamp__gte=start, timestamp__lt=end)
    counts = rows.aggregate(samples=Count('pk'), present_samples=Count('pk', filter=Q(present=True)))
    latest = rows.values('timestamp', 'present', 'confidence').first()
    return {**counts, 'absent_samples': counts['samples'] - counts['present_samples'],
            'present_percent': round(100 * counts['present_samples'] / counts['samples'], 1) if counts['samples'] else None,
            'latest_at': latest['timestamp'] if latest else None,
            'latest_present': latest['present'] if latest else None,
            'latest_confidence': latest['confidence'] if latest else None}


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
