import random
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    CameraAnalytics,
    ComputerActivity,
    ConsentRecord,
    Department,
    Employee,
    Task,
)


class Command(BaseCommand):
    help = "Test data: 3 department, 5 employee, 20 task, activity, camera"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear", action="store_true",
            help="Delete existing productivity data before creating seed data.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["clear"] and any(model.objects.exists() for model in (
            Department, Employee, Task, ConsentRecord, ComputerActivity, CameraAnalytics
        )):
            raise CommandError(
                "Database already contains productivity data. Use --clear to replace it."
            )

        if options["clear"]:
            for model in (CameraAnalytics, ComputerActivity, Task,
                          ConsentRecord, Employee, Department):
                model.objects.all().delete()

        rng = random.Random(42)
        today = timezone.localdate()

        depts = [Department.objects.create(name=n) for n in ["IT", "HR", "Sales"]]

        employees = []
        for i, name in enumerate(["Bat", "Dorj", "Saraa", "Tuya", "Ganaa"]):
            emp = Employee.objects.create(
                department=depts[i % 3],
                full_name=name,
                email=f"{name.lower()}@example.com",
            )
            employees.append(emp)
            for ctype in ("computer", "camera"):
                ConsentRecord.objects.create(
                    employee=emp, consent_type=ctype,
                    is_granted=True, granted_at=timezone.now(),
                )

        statuses = ["todo", "in_progress", "done"]
        for i in range(20):
            Task.objects.create(
                employee=rng.choice(employees),
                title=f"Task {i + 1}",
                status=rng.choice(statuses),
                due_date=today + timedelta(days=rng.randint(1, 30)),
            )

        apps = ["chrome.exe", "code.exe", "excel.exe", "teams.exe"]
        for emp in employees:
            for d in range(7):
                ComputerActivity.objects.create(
                    employee=emp,
                    date=today - timedelta(days=d),
                    active_seconds=rng.randint(14000, 26000),
                    idle_seconds=rng.randint(1000, 6000),
                    key_count=rng.randint(3000, 15000),
                    click_count=rng.randint(1000, 6000),
                    app_name=rng.choice(apps),
                )
            for h in range(8):
                CameraAnalytics.objects.create(
                    employee=emp,
                    observed_at=timezone.now() - timedelta(hours=h),
                    is_at_desk=rng.random() > 0.2,
                    confidence=round(rng.uniform(0.6, 0.99), 2),
                )

        self.stdout.write(self.style.SUCCESS(
            "Seed duuslaa: 5 employee, 20 task, activity, camera"))
