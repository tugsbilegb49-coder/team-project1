from datetime import datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from scoring.models import ProductivityScore
from users.models import Department, User
from .charts import day_timeline, presence_by_hour, score_trend, time_split
from .models import CameraPresence, ComputerActivity


def at(day, hour, minute=0):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


def score(person, day, value, t=100, q=80, d=100, w=50):
    return ProductivityScore.objects.create(
        employee=person,
        date=day,
        task_completion=Decimal(t),
        quality=Decimal(q),
        deadline_completion=Decimal(d),
        work_process=Decimal(w),
        score=Decimal(value),
        category='MEDIUM',
    )


class DayChartTests(TestCase):
    def setUp(self):
        self.person = User.objects.create_user('chart-person')
        self.day = timezone.localdate()
        for start, seconds, application, category in (
            (at(self.day, 9, 10), 600, 'Code', 'WORK'),  # 09:10–09:20 crosses into the 09:15 slot.
            (at(self.day, 9, 20), 120, 'Slack', 'COMMUNICATION'),
            (at(self.day, 9, 22), 180, 'Idle', 'OTHER'),
        ):
            ComputerActivity.objects.create(
                employee=self.person,
                started_at=start,
                duration_seconds=seconds,
                application=application,
                category=category,
            )

    def test_the_day_splits_into_work_other_and_idle(self):
        self.assertEqual(time_split(self.person, self.day), {'work': 600, 'other': 120, 'idle': 180})

    def test_the_timeline_puts_each_second_in_its_quarter_hour(self):
        self.assertEqual(
            day_timeline(self.person, self.day),
            [
                {'slot': 36, 'start': '09:00', 'work': 300, 'other': 0, 'idle': 0},
                {'slot': 37, 'start': '09:15', 'work': 300, 'other': 120, 'idle': 180},
            ],
        )

    def test_camera_samples_are_counted_per_local_hour(self):
        for minute, present in ((5, True), (30, False)):
            CameraPresence.objects.create(
                employee=self.person, timestamp=at(self.day, 9, minute), present=present, confidence=0.8
            )
        CameraPresence.objects.create(employee=self.person, timestamp=at(self.day, 10), present=True, confidence=0.9)
        self.assertEqual(
            presence_by_hour(self.person, self.day),
            [{'hour': 9, 'present': 1, 'absent': 1}, {'hour': 10, 'present': 1, 'absent': 0}],
        )

    def test_the_score_trend_covers_the_last_30_days(self):
        for back, value in ((0, 70), (1, 60), (40, 10)):
            score(self.person, self.day - timedelta(days=back), value)
        trend = score_trend(self.person, self.day)
        self.assertEqual([row['score'] for row in trend], [60.0, 70.0])
        self.assertEqual(trend[-1]['quality'], 80.0)

    def test_the_pages_receive_the_chart_data(self):
        client = APIClient()
        client.force_authenticate(self.person)
        today = client.get('/api/me/today/').data
        self.assertEqual(today['split']['work'], 600)
        self.assertEqual(len(today['timeline']), 2)
        dashboard = client.get('/api/scores/dashboard/', {'date': self.day.isoformat()}).data
        self.assertEqual(dashboard['score_trend'], [])
        self.assertEqual(dashboard['presence_by_hour'], [])


class MonthChartTests(TestCase):
    def test_people_departments_and_busy_hours_are_compared_within_scope(self):
        sales, office = Department.objects.create(name='Борлуулалт'), Department.objects.create(name='Оффис')
        admin = User.objects.create_user('chart-admin', role='ADMIN')
        manager = User.objects.create_user('chart-manager', role='MANAGER', department=sales)
        seller = User.objects.create_user('chart-seller', department=sales, first_name='Сараа')
        clerk = User.objects.create_user('chart-clerk', department=office)
        day = timezone.localdate().replace(day=3)
        score(seller, day, 80)
        score(seller, day + timedelta(days=1), 60)
        score(clerk, day, 50)
        ComputerActivity.objects.create(
            employee=seller, started_at=at(day, 10, 5), duration_seconds=900, application='Excel', category='WORK'
        )
        ComputerActivity.objects.create(
            employee=seller, started_at=at(day, 10, 30), duration_seconds=600, application='Idle', category='OTHER'
        )
        client = APIClient()
        client.force_authenticate(admin)
        data = client.get('/api/reports/charts/', {'month': day.strftime('%Y-%m')}).data
        rows = {row['name']: row for row in data['employees']}
        self.assertEqual((rows['Сараа']['average_score'], rows['Сараа']['scored_days']), (70.0, 2))
        self.assertEqual(rows['Сараа']['work_seconds'], 900)  # Idle is not work.
        self.assertIsNone(rows['chart-admin']['average_score'])
        departments = {row['department']: row for row in data['departments']}
        self.assertEqual(departments['Борлуулалт']['average_score'], 70.0)
        self.assertEqual(departments['Оффис']['average_score'], 50.0)
        self.assertEqual(data['heatmap'][day.isoweekday() - 1][10], 900)
        client.force_authenticate(manager)
        seen = {
            row['name']
            for row in client.get('/api/reports/charts/', {'month': day.strftime('%Y-%m')}).data['employees']
        }
        self.assertEqual(seen, {'chart-manager', 'Сараа'})  # Only the manager's own department.
        self.assertEqual(client.get('/api/reports/charts/', {'month': '2026-13'}).status_code, 400)
