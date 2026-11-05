import csv
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import User
from .models import ActivityEvent


class ImportActivityLogTests(TestCase):
    def setUp(self):
        self.employee = User.objects.create_user(username="employee", password="safe-password-123")

    def test_imports_csv_and_skips_duplicate_rows(self):
        with TemporaryDirectory() as directory:
            log_path = Path(directory) / "activity_log.csv"
            with log_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["timestamp", "state", "duration_seconds"])
                writer.writeheader()
                writer.writerow({
                    "timestamp": datetime(2026, 11, 5, 9, 0).isoformat(),
                    "state": "WORKING",
                    "duration_seconds": "120.0",
                })

            call_command("import_activity_log", str(log_path), employee="employee")
            call_command("import_activity_log", str(log_path), employee="employee")

        self.assertEqual(ActivityEvent.objects.count(), 1)
        self.assertEqual(ActivityEvent.objects.get().state, ActivityEvent.State.WORKING)


class ComputerActivityIngestTests(TestCase):
    def setUp(self):
        self.employee = User.objects.create_user(username="employee", password="safe-password-123")
        self.client = APIClient()
        self.client.force_authenticate(self.employee)

    def test_employee_agent_can_only_write_an_event_for_itself(self):
        device = self.employee.devices.create(name="Test laptop", platform="Darwin")
        response = self.client.post(
            "/api/computer-activity/ingest/",
            {
                "started_at": timezone.now().isoformat(),
                "duration_seconds": 30,
                "application": "Visual Studio Code",
                "category": "WORK",
                "device_id": str(device.pk),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["employee"], self.employee.pk)


class CameraActivityIngestTests(TestCase):
    def setUp(self):
        self.employee = User.objects.create_user(username="employee", password="safe-password-123")
        self.client = APIClient()
        self.client.force_authenticate(self.employee)

    def test_employee_camera_can_only_write_an_event_for_itself(self):
        response = self.client.post(
            "/api/activity-events/ingest/",
            {
                "timestamp": timezone.now().isoformat(),
                "state": "WORKING",
                "duration_seconds": 30,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["employee"], self.employee.pk)
        self.assertEqual(response.data["state"], "WORKING")

    @override_settings(REQUIRE_MONITORING_CONSENT=True)
    def test_consent_is_required_when_production_flag_is_enabled(self):
        response = self.client.post(
            "/api/activity-events/ingest/",
            {"timestamp": timezone.now().isoformat(), "state": "WORKING", "duration_seconds": 30},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
