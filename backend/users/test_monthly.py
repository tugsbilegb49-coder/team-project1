from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from activity.models import ComputerActivity, ArchivedMonthlyActivity
from workforce.models import Task, TaskContribution, TaskWorkSession, TaskTransfer
from .models import User, Department, Device, ConsentRecord, LauncherInterval
from .monthly import ZONE


def dt(value):
    return datetime.fromisoformat(value).replace(tzinfo=ZONE)


class MonthlyTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name='Engineering')
        self.admin = User.objects.create_user('monthly-admin', role='ADMIN')
        self.manager = User.objects.create_user('monthly-manager', role='MANAGER', department=self.department)
        self.employee = User.objects.create_user('monthly-worker', department=self.department)
        self.other = User.objects.create_user('monthly-other')
        self.device = Device.objects.create(employee=self.employee, name='Laptop', platform='test')
        Device.objects.filter(pk=self.device.pk).update(created_at=dt('2026-10-01'))
        ConsentRecord.objects.create(employee=self.employee, granted=True, policy_version='2026-11')
        self.client = APIClient()
        self.client.force_authenticate(self.employee)
        self.now = dt('2026-11-15T12:00:00')
        self.time = patch('users.monthly.timezone.now', return_value=self.now)
        self.time.start(); self.addCleanup(self.time.stop)

    def upload(self, items, **extra):
        return self.client.post('/api/launcher-usage/', {'device_id': str(self.device.pk), 'intervals': items, **extra}, format='json')

    def interval(self, start='2026-11-01T01:00:00', end='2026-11-01T01:10:00'):
        return {'event_id': str(uuid4()), 'started_at': dt(start).isoformat(), 'ended_at': dt(end).isoformat()}

    def report(self, month='2026-11'):
        response = self.client.get('/api/reports/monthly/', {'month':month})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['employees']

    def test_replay_extension_out_of_order_and_identity_are_atomic(self):
        item = self.interval()
        self.assertEqual(self.upload([item]).status_code, 200)
        self.assertEqual(self.upload([item, item]).status_code, 200)
        longer = {**item, 'ended_at': dt('2026-11-01T01:20:00').isoformat()}
        self.assertEqual(self.upload([longer]).status_code, 200)
        self.assertEqual(self.upload([item]).status_code, 200)
        self.assertEqual(self.report()[0]['launcher_seconds'], 1200)
        changed = {**item, 'started_at': dt('2026-11-01T01:01:00').isoformat()}
        self.assertEqual(self.upload([self.interval(), changed]).status_code, 400)
        self.assertEqual(LauncherInterval.objects.count(), 1)

    def test_rejects_other_owner_disabled_consent_future_and_extra_fields(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.upload([]).status_code, 403)
        ConsentRecord.objects.create(employee=self.other, granted=True, policy_version='2026-11')
        self.assertEqual(self.upload([]).status_code, 403)
        self.client.force_authenticate(self.employee)
        self.assertEqual(self.upload([], employee_id=self.other.pk).status_code, 400)
        self.assertEqual(self.upload([self.interval(end='2026-11-01T03:00:00')]).status_code, 400)
        self.assertEqual(self.upload([self.interval(start='2026-12-01T00:00:00', end='2026-12-01T00:00:05')]).status_code, 400)
        self.assertEqual(self.upload([self.interval(start='2026-09-01T00:00:00', end='2026-09-01T00:00:05')]).status_code, 400)
        Device.objects.filter(pk=self.device.pk).update(enabled=False)
        self.assertEqual(self.upload([]).status_code, 403)
        Device.objects.filter(pk=self.device.pk).update(enabled=True)
        ConsentRecord.objects.filter(employee=self.employee).update(revoked_at=self.now)
        self.assertEqual(self.upload([]).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/reports/monthly/').status_code, 401)

    def test_month_splits_and_device_overlap_is_not_double_counted(self):
        self.assertEqual(self.upload([self.interval('2026-10-31T23:59:50', '2026-11-01T00:00:10')]).status_code, 200)
        device = Device.objects.create(employee=self.employee, name='Second', platform='test')
        LauncherInterval.objects.create(employee=self.employee, device=device, event_id=uuid4(),
            started_at=dt('2026-11-01T00:00:05'), ended_at=dt('2026-11-01T00:00:20'))
        self.assertEqual(self.report('2026-10')[0]['launcher_seconds'], 10)
        self.assertEqual(self.report()[0]['launcher_seconds'], 20)
        self.assertEqual(self.report('2026-12')[0]['launcher_seconds'], 0)

    def test_roles_only_see_allowed_employees(self):
        self.assertEqual({row['employee'] for row in self.report()}, {self.employee.pk})
        self.client.force_authenticate(self.manager)
        self.assertEqual({row['employee'] for row in self.report()}, {self.employee.pk, self.manager.pk})
        self.manager.department = None; self.manager.save()
        self.assertEqual({row['employee'] for row in self.report()}, {self.manager.pk})
        self.client.force_authenticate(self.admin)
        self.assertEqual(len(self.report()), 4)

    def test_invalid_month_is_not_silently_current_month(self):
        for month in ('2026-13', '26-11', '2026-1', '2026-11-01', '9999-12'):
            self.assertEqual(self.client.get('/api/reports/monthly/', {'month':month}).status_code, 400)

    def test_apps_tasks_and_transfers_are_separate_and_month_clipped(self):
        ComputerActivity.objects.create(employee=self.employee, started_at=dt('2026-10-31T23:59:50'),
            duration_seconds=30, application='Code')
        ComputerActivity.objects.create(employee=self.employee, started_at=dt('2026-11-01T00:01:00'),
            duration_seconds=40, application='Idle')
        task = Task.objects.create(employee=self.employee, title='Completed work', status='DONE', completed_at=dt('2026-11-02'))
        contribution = TaskContribution.objects.create(task=task, employee=self.employee, employee_name='worker', percent=35)
        TaskWorkSession.objects.create(contribution=contribution, employee=self.employee,
            started_at=dt('2026-10-31T23:59:50'), last_heartbeat=dt('2026-11-01T00:00:20'), ended_at=dt('2026-11-01T00:00:30'))
        TaskTransfer.objects.create(task=task, from_employee=self.other, to_employee=self.employee,
            from_name='other', to_name='worker', status='ACCEPTED', responded_at=dt('2026-11-01'))
        row = self.report()[0]
        self.assertEqual((row['application_seconds'], row['idle_seconds'], row['tracked_seconds']), (20, 40, 60))
        self.assertEqual(row['task_seconds'], 30)
        self.assertEqual(row['tasks'][0]['contribution_percent'], '35.00')
        self.assertEqual(len(row['completed_tasks']), 1)
        self.assertEqual((row['transfers_sent'], row['transfers_received']), (0, 1))
        self.assertIsNone(row['launcher_recorded_since'])
        self.assertEqual(self.report('2026-10')[0]['task_seconds'], 10)

    def test_abandoned_task_timer_is_capped_at_heartbeat_lease(self):
        task = Task.objects.create(employee=self.employee, title='No browser')
        contribution = TaskContribution.objects.create(task=task, employee=self.employee, employee_name='worker')
        TaskWorkSession.objects.create(contribution=contribution, employee=self.employee,
            started_at=dt('2026-11-01'), last_heartbeat=dt('2026-11-01')+timedelta(seconds=10))
        self.assertEqual(self.report()[0]['task_seconds'], 100)

    def test_retention_preserves_month_totals_exactly_once_including_cross_month(self):
        ComputerActivity.objects.create(employee=self.employee, started_at=dt('2026-08-31T23:59:50'),
            duration_seconds=30, application='Code')
        before = self.report('2026-09')[0]['application_seconds']
        call_command('cleanup_activity', days=1, apply=True, stdout=StringIO())
        self.assertFalse(ComputerActivity.objects.exists())
        self.assertEqual(ArchivedMonthlyActivity.objects.count(), 2)
        self.assertEqual(self.report('2026-08')[0]['application_seconds'], 10)
        self.assertEqual(self.report('2026-09')[0]['application_seconds'], before)
        call_command('cleanup_activity', days=1, apply=True, stdout=StringIO())
        self.assertEqual(self.report('2026-09')[0]['application_seconds'], before)
        # A long-offline queue can replay an already archived segment.
        response = self.client.post('/api/computer-activity/ingest/', {
            'started_at': dt('2026-08-31T23:59:50').isoformat(), 'duration_seconds':30,
            'application':'Code', 'category':'WORK'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(ComputerActivity.objects.exists())
        self.assertEqual(self.report('2026-09')[0]['application_seconds'], before)
