"""The organisation's working schedule (Тохиргоо → Ажлын хуваарь), for example Mon–Fri 14:00–20:00.

For students the hours outside it are classes: reminders stay quiet then, the work-programs share
of the score (W) is taken from the schedule's hours, and reports show time outside it separately.
"""

from datetime import datetime, time, timedelta

from django.utils import timezone

DEFAULT_DAYS = [0, 1, 2, 3, 4]  # Monday … Friday
DEFAULT_START, DEFAULT_END = time(9), time(18)


def default_work_days():
    return list(DEFAULT_DAYS)


class Schedule:
    def __init__(self, days, start, end):
        self.days = set(days or [])
        self.start, self.end = start or DEFAULT_START, end or DEFAULT_END

    @classmethod
    def current(cls):
        from users.operations import current_settings

        policy = current_settings()
        return cls(policy.work_days, policy.work_start, policy.work_end)

    def window(self, day):
        """The working hours of `day` as aware datetimes, or None on a day off."""
        if day.weekday() not in self.days:
            return None
        return (
            timezone.make_aware(datetime.combine(day, self.start)),
            timezone.make_aware(datetime.combine(day, self.end)),
        )

    def inside_seconds(self, started, duration):
        """How much of [started, started + duration) falls inside the working hours."""
        local = timezone.localtime(started)
        window = self.window(local.date())
        if window is None:
            return 0.0
        left, right = max(started, window[0]), min(started + timedelta(seconds=duration), window[1])
        return max(0.0, (right - left).total_seconds())

    def as_dict(self):
        return {'days': sorted(self.days), 'start': self.start.strftime('%H:%M'), 'end': self.end.strftime('%H:%M')}
