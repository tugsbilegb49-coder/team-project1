from datetime import datetime, time, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from scoring.services import calculate_daily_score
from users.models import AuditEntry, MonitoringSettings, User
from .charts import outside_schedule_seconds
from .models import ComputerActivity
from .schedule import Schedule


def at(day, hour, minute=0):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


def weekday():
    day = timezone.localdate() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


class ScheduleTests(TestCase):
    def setUp(self):
        MonitoringSettings.objects.update_or_create(
            pk=1, defaults={'work_days': [0, 1, 2, 3, 4], 'work_start': time(14), 'work_end': time(20)}
        )
        self.student = User.objects.create_user('student')
        self.day = weekday()

    def add(self, hour, minutes, application, category):
        ComputerActivity.objects.create(
            employee=self.student,
            started_at=at(self.day, hour),
            duration_seconds=minutes * 60,
            application=application,
            category=category,
        )

    def test_only_the_schedules_hours_count_as_inside(self):
        schedule = Schedule.current()
        self.assertEqual(schedule.inside_seconds(at(self.day, 13, 50), 1200), 600)  # 13:50–14:10 → 10 min in.
        self.assertEqual(schedule.inside_seconds(at(self.day, 10), 600), 0)
        saturday = self.day + timedelta(days=(5 - self.day.weekday()))
        self.assertEqual(schedule.inside_seconds(at(saturday, 15), 600), 0)
        self.assertEqual(schedule.as_dict(), {'days': [0, 1, 2, 3, 4], 'start': '14:00', 'end': '20:00'})

    def test_class_hours_do_not_lower_the_work_share_of_the_score(self):
        self.add(9, 120, 'Google Chrome', 'BROWSER')  # Morning classes, outside the schedule.
        self.add(15, 90, 'Visual Studio Code', 'WORK')
        self.add(17, 30, 'Slack', 'COMMUNICATION')
        score = calculate_daily_score(self.student, self.day)
        self.assertEqual(float(score.work_process), 75.0)  # 90 of the 120 scheduled minutes, not 90 of 240.
        self.assertEqual(outside_schedule_seconds(self.student, self.day), 120 * 60)

    def test_a_day_with_nothing_inside_the_schedule_uses_the_whole_day(self):
        self.add(9, 60, 'Visual Studio Code', 'WORK')
        self.add(10, 60, 'Google Chrome', 'BROWSER')
        self.assertEqual(float(calculate_daily_score(self.student, self.day).work_process), 50.0)

    def test_pages_show_the_schedule_and_time_outside_it(self):
        self.add(9, 60, 'Google Chrome', 'BROWSER')
        client = APIClient()
        client.force_authenticate(self.student)
        month = self.day.strftime('%Y-%m')
        row = next(
            row
            for row in client.get('/api/reports/monthly/', {'month': month}).data['employees']
            if row['username'] == 'student'
        )
        self.assertEqual(row['outside_schedule_seconds'], 3600)
        today = client.get('/api/me/today/').data
        self.assertEqual(today['schedule']['start'], '14:00')

    def test_admin_sets_the_schedule_and_a_backwards_one_is_refused(self):
        admin = User.objects.create_user('schedule-admin', role='ADMIN')
        client = APIClient()
        client.force_authenticate(admin)
        version = client.get('/api/monitoring-settings/').data['version']
        bad = client.patch(
            '/api/monitoring-settings/',
            {'expected_version': version, 'work_start': '20:00', 'work_end': '08:00'},
            format='json',
        )
        self.assertEqual(bad.status_code, 400)
        good = client.patch(
            '/api/monitoring-settings/',
            {'expected_version': version, 'work_days': [4, 0, 0], 'work_start': '13:30', 'work_end': '19:00'},
            format='json',
        )
        self.assertEqual(good.status_code, 200, good.data)
        self.assertEqual((good.data['work_days'], str(good.data['work_start'])[:5]), ([0, 4], '13:30'))
        change = AuditEntry.objects.filter(resource='monitoring_settings').latest('created_at').changes
        self.assertEqual(change['work_start'], {'before': '14:00:00', 'after': '13:30:00'})
