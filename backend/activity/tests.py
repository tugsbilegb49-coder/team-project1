import csv
from datetime import datetime, timedelta
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


@override_settings(REQUIRE_MONITORING_CONSENT=False)
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
                "started_at": (timezone.now() - timedelta(seconds=30)).isoformat(),
                "duration_seconds": 30,
                "application": "Visual Studio Code",
                "category": "WORK",
                "device_id": str(device.pk),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["employee"], self.employee.pk)


@override_settings(REQUIRE_MONITORING_CONSENT=False)
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


@override_settings(REQUIRE_MONITORING_CONSENT=False)
class SegmentValidationTests(TestCase):
    def setUp(self):
        self.employee = User.objects.create_user(username='validation-worker')
        self.client = APIClient()
        self.client.force_authenticate(self.employee)
        self.start = timezone.now() - timedelta(minutes=10)

    def computer(self, **changes):
        data = {'started_at': self.start.isoformat(), 'duration_seconds': 30,
                'application': 'Code', 'category': 'WORK'}
        data.update(changes)
        return self.client.post('/api/computer-activity/ingest/', data, format='json')

    def test_rejects_future_start_and_unfinished_segment(self):
        self.assertEqual(self.computer(started_at=(timezone.now()+timedelta(seconds=1)).isoformat()).status_code,400)
        self.assertEqual(self.computer(started_at=(timezone.now()-timedelta(seconds=5)).isoformat()).status_code,400)

    def test_rejects_zero_negative_excessive_and_nonfinite_duration(self):
        for value in (0, -1, 3601, 'NaN', 'Infinity'):
            with self.subTest(duration=value):
                self.assertEqual(self.computer(duration_seconds=value).status_code,400)
        self.assertEqual(self.employee.computer_activities.count(),0)

    def test_exact_retry_is_idempotent_but_other_app_cannot_overlap(self):
        self.assertEqual(self.computer().status_code,201)
        self.assertEqual(self.computer().status_code,200)
        self.assertEqual(self.computer(application='Safari',category='BROWSER').status_code,400)
        self.assertEqual(self.employee.computer_activities.count(),1)

    def test_adjacent_intervals_allowed_but_different_devices_still_cannot_overlap(self):
        self.assertEqual(self.computer().status_code,201)
        device=self.employee.devices.create(name='Second device',platform='test')
        self.assertEqual(self.computer(started_at=(self.start+timedelta(seconds=29)).isoformat(),device_id=str(device.pk)).status_code,400)
        self.assertEqual(self.computer(started_at=(self.start+timedelta(seconds=30)).isoformat()).status_code,201)

    def test_camera_uses_end_timestamp_and_keeps_separate_stream(self):
        self.computer()
        data={'timestamp':(self.start+timedelta(seconds=30)).isoformat(),'duration_seconds':30,'state':'WORKING'}
        endpoint='/api/activity-events/ingest/'
        self.assertEqual(self.client.post(endpoint,data,format='json').status_code,201)
        self.assertEqual(self.client.post(endpoint,data,format='json').status_code,200)
        self.assertEqual(self.client.post(endpoint,{**data,'state':'PHONE'},format='json').status_code,400)
        data['timestamp']=(self.start+timedelta(seconds=60)).isoformat()
        self.assertEqual(self.client.post(endpoint,data,format='json').status_code,201)
        data['timestamp']=(timezone.now()+timedelta(seconds=1)).isoformat()
        self.assertEqual(self.client.post(endpoint,data,format='json').status_code,400)

    def test_camera_accepts_rounding_jitter_but_rejects_real_overlap(self):
        endpoint='/api/activity-events/ingest/'
        end=self.start+timedelta(seconds=30)
        data={'timestamp':end.isoformat(),'duration_seconds':30,'state':'WORKING'}
        self.assertEqual(self.client.post(endpoint,data,format='json').status_code,201)
        data['timestamp']=(end+timedelta(seconds=29.95)).isoformat()
        self.assertEqual(self.client.post(endpoint,data,format='json').status_code,201)
        data['timestamp']=(end+timedelta(seconds=59)).isoformat()
        self.assertEqual(self.client.post(endpoint,data,format='json').status_code,400)

    def test_admin_crud_cannot_bypass_checks_or_move_ownership(self):
        self.employee.role='ADMIN'
        self.employee.save(update_fields=['role'])
        response=self.client.post('/api/computer-activity/', {'employee':self.employee.pk,'started_at':self.start.isoformat(),
            'duration_seconds':30,'application':'Code','category':'WORK'},format='json')
        self.assertEqual(response.status_code,201)
        endpoint=f'/api/computer-activity/{response.data["id"]}/'
        self.assertEqual(self.client.patch(endpoint,{'application':'VS Code'},format='json').status_code,200)
        self.assertEqual(self.client.patch(endpoint,{'duration_seconds':3601},format='json').status_code,400)
        other=User.objects.create_user('other-worker')
        self.assertEqual(self.client.patch(endpoint,{'employee':other.pk},format='json').status_code,400)
        self.assertEqual(self.computer(started_at=(self.start+timedelta(seconds=40)).isoformat()).status_code,201)
        self.assertEqual(self.client.patch(endpoint,{'duration_seconds':60},format='json').status_code,400)

    def batch(self, **changes):
        data={'schema_version':'1.0','agent_version':'test','employee_id':self.employee.username,'device_id':'batch-test',
            'period_start':self.start.isoformat(),'period_end':(self.start+timedelta(seconds=60)).isoformat(),
            'active_seconds':60,'idle_seconds':0,'keyboard_events':0,'mouse_events':0,
            'apps':[{'name':'A','seconds':30},{'name':'B','seconds':30}]}
        data.update(changes)
        return self.client.post('/api/v1/activity',data,format='json')

    def test_batch_overlap_rolls_back_all_new_segments_and_device(self):
        self.computer(started_at=(self.start+timedelta(seconds=45)).isoformat(),duration_seconds=10)
        self.assertEqual(self.batch().status_code,400)
        self.assertEqual(self.employee.computer_activities.count(),1)
        self.assertEqual(self.employee.devices.count(),0)

    def test_batch_rejects_future_end_and_replays_valid_data(self):
        self.assertEqual(self.batch(period_start=timezone.now().isoformat(),period_end=(timezone.now()+timedelta(seconds=60)).isoformat()).status_code,400)
        self.assertEqual(self.batch().status_code,201)
        self.assertEqual(self.batch().status_code,200)
        self.assertEqual(self.employee.computer_activities.count(),2)
