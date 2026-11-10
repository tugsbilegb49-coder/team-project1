from datetime import datetime, time, timedelta

from django.utils import timezone


def local_datetime_bounds(start_date=None, end_date=None):
    """Convert inclusive local calendar dates to an index-friendly datetime range."""
    tz = timezone.get_current_timezone()
    start_at = (
        timezone.make_aware(datetime.combine(start_date, time.min), tz)
        if start_date
        else None
    )
    end_at = (
        timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), tz)
        if end_date
        else None
    )
    return start_at, end_at
