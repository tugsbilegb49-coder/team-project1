from datetime import date, datetime, time
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from activity.models import ActivityEvent, ComputerActivity
from users.models import User
from workforce.models import Task
from .models import ProductivityScore
from .services import calculate_daily_score


class DailyScoreTests(TestCase):
    def setUp(self):
        self.employee = User.objects.create_user(username="employee", password="safe-password-123")
        self.score_date = date(2026, 11, 5)
        completed_at = timezone.make_aware(datetime.combine(self.score_date, time(9, 0)))
        Task.objects.create(
            employee=self.employee,
            title="Finished task",
            due_date=self.score_date,
            status=Task.Status.DONE,
            completed_at=completed_at,
            quality_score=80,
        )
        Task.objects.create(
            employee=self.employee,
            title="Unfinished task",
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
        self.assertEqual(score.task_completion, Decimal("50.00"))
        self.assertEqual(score.quality, Decimal("80.00"))
        self.assertEqual(score.deadline_completion, Decimal("50.00"))
        self.assertEqual(score.work_process, Decimal("50.00"))
        self.assertEqual(score.score, Decimal("59.00"))
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
            application="Visual Studio Code",
            category=ComputerActivity.Category.WORK,
        )
        ComputerActivity.objects.create(
            employee=self.employee,
            started_at=timezone.make_aware(datetime.combine(self.score_date, time(13, 30))),
            duration_seconds=1800,
            application="Safari",
            category=ComputerActivity.Category.BROWSER,
        )
        score = calculate_daily_score(self.employee, self.score_date)
        self.assertEqual(score.work_process, Decimal("75.00"))

    def test_dashboard_endpoint_returns_daily_aggregates(self):
        calculate_daily_score(self.employee, self.score_date)
        client = APIClient()
        client.force_authenticate(self.employee)
        response = client.get(f"/api/scores/dashboard/?date={self.score_date.isoformat()}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["employee"]["username"], "employee")
        self.assertEqual(response.data["score"]["score"], "59.00")
        self.assertEqual(response.data["camera"][0]["state"], "IDLE")

