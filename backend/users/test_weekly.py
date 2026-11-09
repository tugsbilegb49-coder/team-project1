from datetime import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from activity.models import ComputerActivity
from workforce.models import Task, TaskContribution, TaskWorkSession
from .models import User
from .monthly import ZONE


def dt(value):
    return datetime.fromisoformat(value).replace(tzinfo=ZONE)


class MyWeekTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('week-worker')
        self.other = User.objects.create_user('week-other')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def session(self, user, title, started, ended, status='IN_PROGRESS'):
        task = Task.objects.create(employee=user, title=title, status=status)
        contribution = TaskContribution.objects.create(task=task, employee=user, employee_name=user.username)
        TaskWorkSession.objects.create(
            contribution=contribution,
            employee=user,
            started_at=dt(started),
            last_heartbeat=dt(ended),
            ended_at=dt(ended),
        )
        return task

    def test_splits_time_by_day_and_task_for_the_monday_week(self):
        # Wednesday input still returns Monday 2026-10-05 .. Sunday 2026-10-11.
        self.session(self.user, 'Report', '2026-10-05T23:30:00', '2026-10-06T00:30:00')
        self.session(self.user, 'Design', '2026-10-07T09:00:00', '2026-10-07T11:00:00')
        self.session(self.user, 'Outside week', '2026-10-12T09:00:00', '2026-10-12T10:00:00')
        self.session(self.other, 'Not mine', '2026-10-07T09:00:00', '2026-10-07T17:00:00')
        ComputerActivity.objects.create(
            employee=self.user, started_at=dt('2026-10-04T23:59:30'), duration_seconds=60, application='Code'
        )
        ComputerActivity.objects.create(
            employee=self.user, started_at=dt('2026-10-07T12:00:00'), duration_seconds=600, application='Idle'
        )
        done = Task.objects.create(
            employee=self.user, title='Shipped', status='DONE', completed_at=dt('2026-10-08T15:00')
        )

        data = self.client.get('/api/me/week/', {'start': '2026-10-07'}).data

        self.assertEqual((data['start'], data['end']), ('2026-10-05', '2026-10-11'))
        self.assertEqual([day['date'] for day in data['days']][:2], ['2026-10-05', '2026-10-06'])
        by_day = {day['date']: day for day in data['days']}
        self.assertEqual(by_day['2026-10-05']['task_seconds'], 1800)  # Midnight split.
        self.assertEqual(by_day['2026-10-06']['task_seconds'], 1800)
        self.assertEqual(by_day['2026-10-05']['application_seconds'], 30)  # Only the part inside the week.
        self.assertEqual(by_day['2026-10-07']['idle_seconds'], 600)
        self.assertEqual(data['totals'], {'task_seconds': 10800, 'application_seconds': 30, 'idle_seconds': 600})
        self.assertEqual(
            [(row['title'], row['seconds']) for row in data['tasks']], [('Design', 7200), ('Report', 3600)]
        )
        self.assertEqual(data['completed_tasks'], 1)
        self.assertNotIn(done.title, [row['title'] for row in data['tasks']])

    def test_rejects_bad_dates_and_requires_login(self):
        self.assertEqual(self.client.get('/api/me/week/', {'start': 'last-week'}).status_code, 400)
        self.assertEqual(self.client.get('/api/me/week/', {'start': '1999-01-04'}).status_code, 400)
        self.assertEqual(APIClient().get('/api/me/week/').status_code, 401)

    def test_current_week_is_the_default(self):
        data = self.client.get('/api/me/week/').data
        self.assertEqual(len(data['days']), 7)
        self.assertEqual(datetime.fromisoformat(data['start']).weekday(), 0)
