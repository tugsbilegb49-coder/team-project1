from datetime import date, datetime, time
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from activity.models import ActivityEvent, ComputerActivity
from users.models import User
from workforce.models import Task
from .models import ProductivityScore
from .services import calculate_daily_score


class DailyScoreTests(TestCase):
    def setUp(self):
        self.employee = User.objects.create_user(username='employee', password='safe-password-123')
        self.score_date = date(2026, 11, 5)
        completed_at = timezone.make_aware(datetime.combine(self.score_date, time(9, 0)))
        Task.objects.create(
            employee=self.employee,
            title='Finished task',
            due_date=self.score_date,
            status=Task.Status.DONE,
            completed_at=completed_at,
            quality_score=80,
        )
        Task.objects.create(
            employee=self.employee,
            title='Unfinished task',
            due_date=self.score_date,
            status=Task.Status.IN_PROGRESS,
        )
        ActivityEvent.objects.create(
            employee=self.employee,
            timestamp=timezone.make_aware(datetime.combine(self.score_date, time(10, 0))),
            state=ActivityEvent.State.WORKING,
            duration_seconds=3600,
        )
        ActivityEvent.objects.create(
            employee=self.employee,
            timestamp=timezone.make_aware(datetime.combine(self.score_date, time(11, 0))),
            state=ActivityEvent.State.IDLE,
            duration_seconds=3600,
        )

    def test_calculates_weighted_daily_score(self):
        score = calculate_daily_score(self.employee, self.score_date)
        self.assertEqual(score.task_completion, Decimal('50.00'))
        self.assertEqual(score.quality, Decimal('80.00'))
        self.assertEqual(score.deadline_completion, Decimal('50.00'))
        self.assertEqual(score.work_process, Decimal('50.00'))
        self.assertEqual(score.score, Decimal('59.00'))
        self.assertEqual(score.category, ProductivityScore.Category.LOW)

    def test_recalculation_updates_existing_daily_score(self):
        first = calculate_daily_score(self.employee, self.score_date)
        second = calculate_daily_score(self.employee, self.score_date)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ProductivityScore.objects.count(), 1)

    def test_desktop_agent_data_is_used_for_work_process_when_available(self):
        ComputerActivity.objects.create(
            employee=self.employee,
            started_at=timezone.make_aware(datetime.combine(self.score_date, time(12, 0))),
            duration_seconds=5400,
            application='Visual Studio Code',
            category=ComputerActivity.Category.WORK,
        )
        ComputerActivity.objects.create(
            employee=self.employee,
            started_at=timezone.make_aware(datetime.combine(self.score_date, time(13, 30))),
            duration_seconds=1800,
            application='Safari',
            category=ComputerActivity.Category.BROWSER,
        )
        score = calculate_daily_score(self.employee, self.score_date)
        self.assertEqual(score.work_process, Decimal('75.00'))

    def test_dashboard_endpoint_returns_daily_aggregates(self):
        calculate_daily_score(self.employee, self.score_date)
        client = APIClient()
        client.force_authenticate(self.employee)
        response = client.get(f'/api/scores/dashboard/?date={self.score_date.isoformat()}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['employee']['username'], 'employee')
        self.assertEqual(response.data['score']['score'], '59.00')
        self.assertEqual(response.data['camera'][0]['state'], 'IDLE')


class CameraMidnightTests(TestCase):
    def setUp(self):
        from datetime import timedelta

        self.employee = User.objects.create_user('midnight-worker')
        self.day = timezone.localdate() - timedelta(days=2)
        self.midnight = timezone.make_aware(datetime.combine(self.day + timedelta(days=1), time.min))

    def test_event_ending_at_midnight_belongs_to_previous_day(self):
        from datetime import timedelta
        from activity.reporting import camera_totals_for_day

        ActivityEvent.objects.create(
            employee=self.employee, timestamp=self.midnight, state='WORKING', duration_seconds=10
        )
        ActivityEvent.objects.create(
            employee=self.employee, timestamp=self.midnight + timedelta(seconds=10), state='IDLE', duration_seconds=10
        )
        self.assertEqual(camera_totals_for_day(self.employee, self.day), {'WORKING': 10})
        self.assertEqual(camera_totals_for_day(self.employee, self.day + timedelta(days=1)), {'IDLE': 10})
        before = calculate_daily_score(self.employee, self.day)
        after = calculate_daily_score(self.employee, self.day + timedelta(days=1))
        self.assertEqual(float(before.work_process), 100)
        self.assertEqual(float(after.work_process), 0)

    def test_existing_unsplit_camera_row_is_apportioned_in_dashboard(self):
        from datetime import timedelta

        ActivityEvent.objects.create(
            employee=self.employee,
            timestamp=self.midnight + timedelta(seconds=10),
            state='WORKING',
            duration_seconds=20,
        )
        client = APIClient()
        client.force_authenticate(self.employee)
        for day in (self.day, self.day + timedelta(days=1)):
            response = client.get('/api/scores/dashboard/', {'date': day.isoformat()})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['camera'], [{'state': 'WORKING', 'seconds': 10}])


class ScorePolicyTests(TestCase):
    def setUp(self):
        from datetime import timedelta

        self.employee = User.objects.create_user('policy-worker')
        self.day = timezone.localdate() - timedelta(days=2)
        self.completed_at = timezone.make_aware(datetime.combine(self.day, time(12)))

    def task(self, **changes):
        data = {
            'employee': self.employee,
            'title': 'Review',
            'due_date': self.day,
            'status': 'DONE',
            'completed_at': self.completed_at,
            'quality_score': 80,
        }
        data.update(changes)
        return Task.objects.create(**data)

    def test_missing_quality_does_not_silently_average_only_rated_tasks(self):
        from .services import ScoreNotReady

        self.task()
        missing = self.task(quality_score=None)
        with self.assertRaises(ScoreNotReady) as context:
            calculate_daily_score(self.employee, self.day)
        self.assertEqual(context.exception.task_ids, [missing.pk])
        self.assertFalse(ProductivityScore.objects.exists())

    def test_explicit_zero_quality_is_valid_and_existing_score_is_not_overwritten_on_error(self):
        from .services import ScoreNotReady

        task = self.task(quality_score=0)
        score = calculate_daily_score(self.employee, self.day)
        self.assertEqual(score.quality, 0)
        previous = score.score
        task.quality_score = None
        task.save()
        with self.assertRaises(ScoreNotReady):
            calculate_daily_score(self.employee, self.day)
        score.refresh_from_db()
        self.assertEqual(score.score, previous)

    def test_later_completion_does_not_rewrite_historical_completion_rate(self):
        from datetime import timedelta

        self.task(completed_at=self.completed_at + timedelta(days=1), quality_score=None)
        score = calculate_daily_score(self.employee, self.day)
        self.assertEqual(score.task_completion, 0)
        self.assertEqual(score.deadline_completion, 0)

    def test_done_task_without_completion_timestamp_is_not_scored(self):
        from .services import ScoreNotReady

        self.task(completed_at=None)
        with self.assertRaises(ScoreNotReady):
            calculate_daily_score(self.employee, self.day)

    def test_api_lists_tasks_that_need_quality(self):
        task = self.task(quality_score=None)
        client = APIClient()
        client.force_authenticate(self.employee)
        response = client.post('/api/scores/calculate/', {'date': self.day.isoformat()}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn(str(task.pk), [str(value) for value in response.data['task_ids']])
        self.assertFalse(ProductivityScore.objects.exists())

    def test_scheduler_command_skips_incomplete_employee_and_continues(self):
        from io import StringIO
        from django.core.management import call_command

        self.task(quality_score=None)
        other = User.objects.create_user('ready-worker')
        Task.objects.create(employee=other, title='Ready', due_date=self.day)  # Something to score.
        out, errors = StringIO(), StringIO()
        call_command('calculate_daily_scores', date=self.day.isoformat(), stdout=out, stderr=errors)
        self.assertTrue(ProductivityScore.objects.filter(employee=other).exists())
        self.assertFalse(ProductivityScore.objects.filter(employee=self.employee).exists())
        self.assertIn('Skipped policy-worker', errors.getvalue())


@override_settings(REQUIRE_MONITORING_CONSENT=False)
class AggregateAgentScoreTests(TestCase):
    def setUp(self):
        from datetime import timedelta

        self.employee = User.objects.create_user('aggregate-worker')
        self.day = timezone.localdate() - timedelta(days=2)
        self.start = timezone.make_aware(datetime.combine(self.day, time(10)))
        self.batch = {
            'schema_version': '1.0',
            'agent_version': 'test',
            'employee_id': self.employee.username,
            'device_id': 'aggregate',
            'period_start': self.start.isoformat(),
            'period_end': (self.start + timedelta(seconds=60)).isoformat(),
            'active_seconds': 42,
            'idle_seconds': 18,
            'keyboard_events': 1,
            'mouse_events': 2,
            'apps': [{'name': 'chrome.exe', 'seconds': 30}, {'name': 'code.exe', 'seconds': 12}],
        }
        self.client = APIClient()
        self.client.force_authenticate(self.employee)

    def test_work_browser_and_idle_determine_actual_work_ratio(self):
        response = self.client.post('/api/v1/activity', self.batch, format='json')
        self.assertEqual(response.status_code, 201)
        rows = ComputerActivity.objects.filter(employee=self.employee)
        self.assertEqual(rows.get(application='code.exe').category, 'WORK')
        self.assertEqual(rows.get(application='chrome.exe').category, 'BROWSER')
        self.assertEqual(rows.get(application='Idle').duration_seconds, 18)
        self.assertEqual(calculate_daily_score(self.employee, self.day).work_process, Decimal('20.00'))
        self.assertEqual(self.client.post('/api/v1/activity', self.batch, format='json').status_code, 200)
        self.assertEqual(rows.count(), 3)

    def test_unknown_active_time_is_not_implicitly_productive(self):
        self.batch['apps'] = [{'name': 'code.exe', 'seconds': 12}]
        self.assertEqual(self.client.post('/api/v1/activity', self.batch, format='json').status_code, 201)
        self.assertEqual(ComputerActivity.objects.get(application='Unattributed activity').duration_seconds, 30)
        self.assertEqual(calculate_daily_score(self.employee, self.day).work_process, Decimal('20.00'))

    def test_server_allowlist_controls_category_and_replay_preserves_original(self):
        with self.settings(PRODUCTIVE_APPLICATIONS=['chrome']):
            self.assertEqual(self.client.post('/api/v1/activity', self.batch, format='json').status_code, 201)
        self.assertEqual(ComputerActivity.objects.get(application='chrome.exe').category, 'WORK')
        self.assertEqual(ComputerActivity.objects.get(application='code.exe').category, 'OTHER')
        self.assertEqual(self.client.post('/api/v1/activity', self.batch, format='json').status_code, 200)
        self.assertEqual(ComputerActivity.objects.count(), 3)
