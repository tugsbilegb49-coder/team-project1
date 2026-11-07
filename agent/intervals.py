"""Split completed intervals at reporting midnight and API duration limits."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

REPORT_TIMEZONE = ZoneInfo('Asia/Ulaanbaatar')


def split_interval(start, end, max_seconds=3600):
    """Yield aware [start, end) intervals belonging to one reporting day each."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError('Timezone-aware timestamps are required.')
    if max_seconds <= 0:
        raise ValueError('max_seconds must be positive.')
    cursor = start.astimezone(timezone.utc)
    finish = end.astimezone(timezone.utc)
    while cursor < finish:
        local = cursor.astimezone(REPORT_TIMEZONE)
        midnight = datetime.combine(local.date() + timedelta(days=1), time.min, REPORT_TIMEZONE)
        boundary = min(finish, midnight.astimezone(timezone.utc), cursor + timedelta(seconds=max_seconds))
        yield cursor, boundary
        cursor = boundary
