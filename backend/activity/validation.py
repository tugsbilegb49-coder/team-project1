"""Time validation shared by admin CRUD and both uploader protocols."""
from datetime import timedelta
import math

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import ComputerActivity, WebsiteActivity

MAX_SEGMENT_SECONDS = 3600


def interval(model, data):
    duration = data['duration_seconds']
    if not math.isfinite(duration) or not 0 < duration <= MAX_SEGMENT_SECONDS:
        raise ValidationError({'duration_seconds': 'Use a finite duration greater than 0 and at most 3600 seconds.'})
    try:
        if model in (ComputerActivity, WebsiteActivity):
            start = data['started_at']
            end = start + timedelta(seconds=duration)
        else:
            # Camera logger timestamps completed segments at their END.
            end = data['timestamp']
            start = end - timedelta(seconds=duration)
    except OverflowError:
        raise ValidationError({'duration_seconds': 'The interval exceeds the supported date range.'})
    if end > timezone.now():
        raise ValidationError({'duration_seconds': 'Activity must finish before the current server time.'})
    return start, end


def lock_employee(employee):
    users = get_user_model().objects
    if connection.vendor == 'sqlite':
        # SQLite ignores SELECT FOR UPDATE; acquire its write lock before reading
        # intervals so concurrent ingestion cannot both pass the overlap check.
        users.filter(pk=employee.pk).update(last_login=F('last_login'))
    else:
        users.select_for_update().get(pk=employee.pk)


def reject_overlap(model, employee, data, exclude_pk=None):
    start, end = interval(model, data)
    field = 'started_at' if model in (ComputerActivity, WebsiteActivity) else 'timestamp'
    rows = model.objects.filter(employee=employee)
    if model in (ComputerActivity, WebsiteActivity):
        rows = rows.filter(started_at__lt=end)
    else:
        rows = rows.filter(timestamp__gt=start)
    if exclude_pk is not None:
        rows = rows.exclude(pk=exclude_pk)
    for timestamp, duration in rows.values_list(field, 'duration_seconds').iterator():
        if model in (ComputerActivity, WebsiteActivity):
            old_start, old_end = timestamp, timestamp + timedelta(seconds=duration)
        else:
            old_start, old_end = timestamp - timedelta(seconds=duration), timestamp
        # Camera duration is rounded to 0.1s by the uploader, while its end
        # timestamp keeps microseconds. Do not reject normal rounding jitter.
        tolerance = 0.05 if model in (ComputerActivity, WebsiteActivity) else 0.1
        overlap = (min(old_end, end) - max(old_start, start)).total_seconds()
        if overlap > tolerance:
            raise ValidationError({'duration_seconds': 'This employee already has overlapping activity in this stream.'})


@transaction.atomic
def save_segment(model, employee, data, device=None):
    lock_employee(employee)
    interval(model, data)
    lookup = {'employee': employee, **data}
    existing = model.objects.filter(**lookup).first()
    if existing is not None:
        return existing, False
    reject_overlap(model, employee, data)
    return model.objects.create(**lookup, device=device), True
def save_website_segment(employee, data, device=None):
    from .models import WebsiteActivity

    lock_employee(employee)
    interval(WebsiteActivity, data)

    lookup = {"employee": employee, **data}
    existing = WebsiteActivity.objects.filter(**lookup).first()

    if existing:
        return existing, False

    reject_overlap(WebsiteActivity, employee, data)

    return WebsiteActivity.objects.create(
        **lookup,
        device=device,
    ), True
