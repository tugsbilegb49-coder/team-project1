import csv
from datetime import date, datetime, time, timedelta
from io import BytesIO, StringIO
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from activity.models import CameraPresence, ComputerActivity
from workforce.models import Task
from .models import AgentHeartbeat, AuditEntry, Department, Device, User
from .operations import current_settings


class OperationalAPITests(TestCase):
    def setUp(self):
        self.team = Department.objects.create(name='Operations team')
        self.admin = User.objects.create_user('operations-admin', role='ADMIN')
        self.manager = User.objects.create_user('operations-manager', role='MANAGER', department=self.team)
        self.worker = User.objects.create_user('operations-worker', department=self.team)
        self.foreign = User.objects.create_user('operations-foreign')
        self.device = Device.objects.create(employee=self.worker, name='Workstation', platform='test')
        self.client = APIClient()

    def test_heartbeat_ownership_online_offline_and_scoped_status(self):
        self.client.force_authenticate(self.worker)
        payload = {
            'device_id': str(self.device.pk),
            'kind': 'computer',
            'queue_count': 4,
            'paused': False,
            'error_code': 'network',
        }
        response = self.client.post('/api/agent-status/heartbeat/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['online'])
        self.assertEqual(response.data['queue_count'], 4)
        beat = AgentHeartbeat.objects.get()
        beat.seen_at = timezone.now() - timedelta(seconds=91)
        beat.save(update_fields=['seen_at'])
        for person, count in ((self.worker, 1), (self.manager, 1), (self.foreign, 0), (self.admin, 1)):
            self.client.force_authenticate(person)
            result = self.client.get('/api/agent-status/').data['results']
            self.assertEqual(len(result), count)
            if count:
                self.assertEqual(result[0]['agents'][0]['state'], 'offline')
        self.client.force_authenticate(self.foreign)
        self.assertEqual(self.client.post('/api/agent-status/heartbeat/', payload, format='json').status_code, 403)

    def test_heartbeat_rejects_private_extra_fields_and_invalid_counts(self):
        self.client.force_authenticate(self.worker)
        data = {'device_id': str(self.device.pk), 'kind': 'camera', 'queue_count': 0, 'paused': True}
        for extra in (
            {'queue_count': -1},
            {'screenshot': 'forbidden'},
            {'error_code': 'raw private error'},
            {'last_upload_at': (timezone.now() + timedelta(days=1)).isoformat()},
        ):
            self.assertEqual(
                self.client.post('/api/agent-status/heartbeat/', {**data, **extra}, format='json').status_code, 400
            )
        self.assertFalse(AgentHeartbeat.objects.exists())

    def test_restarted_agent_preserves_last_known_successful_upload(self):
        self.client.force_authenticate(self.worker)
        last = timezone.now() - timedelta(minutes=5)
        AgentHeartbeat.objects.create(device=self.device, kind='computer', seen_at=last, last_upload_at=last)
        payload = {
            'device_id': str(self.device.pk),
            'kind': 'computer',
            'queue_count': 0,
            'paused': False,
            'last_upload_at': None,
        }
        self.assertEqual(self.client.post('/api/agent-status/heartbeat/', payload, format='json').status_code, 200)
        self.assertEqual(AgentHeartbeat.objects.get().last_upload_at, last)

    def test_settings_require_admin_and_reject_stale_version(self):
        self.client.force_authenticate(self.worker)
        initial = self.client.get('/api/monitoring-settings/').data
        self.assertFalse(initial['automatic_retention'])
        patch = {'expected_version': initial['version'], 'productive_apps': ['Custom Work'], 'camera_threshold': 0.65}
        self.assertEqual(self.client.patch('/api/monitoring-settings/', patch, format='json').status_code, 403)
        self.client.force_authenticate(self.admin)
        saved = self.client.patch('/api/monitoring-settings/', patch, format='json')
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.data['version'], initial['version'] + 1)
        self.assertEqual(self.client.patch('/api/monitoring-settings/', patch, format='json').status_code, 409)
        from activity.classification import category_for_application

        self.assertEqual(category_for_application('Custom Work'), 'WORK')
        self.assertEqual(category_for_application('Visual Studio Code'), 'OTHER')
        self.assertEqual(AuditEntry.objects.filter(resource='monitoring_settings').count(), 1)

    def test_settings_validation_preserves_last_good_values(self):
        self.client.force_authenticate(self.admin)
        version = current_settings().version
        for fields in (
            {'productive_apps': ['Code', 'code']},
            {'camera_threshold': 2},
            {'presence_log_max_bytes': 10},
            {'presence_log_backups': -1},
            {'activity_retention_days': 0},
            {'secret_key': 'forbidden'},
        ):
            response = self.client.patch(
                '/api/monitoring-settings/', {'expected_version': version, **fields}, format='json'
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(current_settings().version, version)

    def test_task_and_role_changes_are_audited_without_passwords(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/tasks/', {'employee': self.worker.pk, 'title': 'Audited task'}, format='json')
        self.assertEqual(response.status_code, 201)
        task_id = response.data['id']
        self.assertEqual(
            self.client.patch(
                f'/api/tasks/{task_id}/', {'status': 'DONE', 'quality_score': '82.50'}, format='json'
            ).status_code,
            200,
        )
        task = Task.objects.get(pk=task_id)
        self.assertIsNotNone(task.completed_at)
        entry = AuditEntry.objects.filter(resource='task', action='update').get()
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.changes['quality_score']['after'], '82.50')
        password = 'New-test-password-not-logged-982!'
        self.assertEqual(
            self.client.patch(
                f'/api/users/{self.worker.pk}/',
                {'password': password, 'role': 'MANAGER', 'department': self.team.pk},
                format='json',
            ).status_code,
            200,
        )
        history = self.client.get('/api/audit/').json()
        self.assertNotIn(password, str(history))
        self.assertNotIn('pbkdf2_', str(history))
        self.assertTrue(AuditEntry.objects.filter(action='password_change').exists())
        self.client.force_authenticate(self.foreign)
        self.assertEqual(self.client.get('/api/audit/').data['count'], 0)
        self.client.force_authenticate(self.worker)
        self.assertGreater(self.client.get('/api/audit/').data['count'], 0)
        self.assertEqual(self.client.patch(f'/api/audit/{entry.pk}/', {}, format='json').status_code, 405)

    def test_notifications_are_scoped_and_disappear_after_resolution(self):
        old = timezone.localdate() - timedelta(days=1)
        task = Task.objects.create(employee=self.worker, title='Overdue task', due_date=old)
        Task.objects.create(employee=self.foreign, title='Foreign task', due_date=old)
        beat = AgentHeartbeat.objects.create(
            device=self.device, kind='computer', seen_at=timezone.now() - timedelta(seconds=100)
        )
        self.client.force_authenticate(self.worker)
        result = self.client.get('/api/notifications/').data
        self.assertEqual({item['kind'] for item in result['items']}, {'task_overdue', 'agent_offline'})
        self.assertNotIn('Foreign task', str(result))
        task.status = 'DONE'
        task.save()
        beat.seen_at = timezone.now()
        beat.save()
        self.assertEqual(self.client.get('/api/notifications/').data['count'], 0)

    def test_csv_and_real_xlsx_export_scope_missing_scores_and_formula_safety(self):
        self.worker.username = '=SUM(1,1)'
        self.worker.save(update_fields=['username'])
        day = date(2026, 11, 5)
        stamp = timezone.make_aware(datetime.combine(day, time(10)))
        ComputerActivity.objects.create(
            employee=self.worker, started_at=stamp, duration_seconds=60, application='Code', category='WORK'
        )
        CameraPresence.objects.create(employee=self.worker, timestamp=stamp, present=True, confidence=0.8)
        self.client.force_authenticate(self.worker)
        query = {'start': str(day), 'end': str(day + timedelta(days=1)), 'employee_id': 'all', 'file_type': 'csv'}
        response = self.client.get('/api/reports/export/', query)
        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['username'], "'=SUM(1,1)")
        self.assertEqual(rows[0]['computer_seconds'], '60.0')
        self.assertEqual(rows[0]['presence_samples'], '1')
        self.assertEqual(rows[0]['score'], '')
        from openpyxl import load_workbook

        response = self.client.get('/api/reports/export/', {**query, 'file_type': 'xlsx'})
        book = load_workbook(BytesIO(response.content), read_only=True, data_only=False)
        try:
            sheet = book['Daily report']
            self.assertEqual(sheet['C2'].value, "'=SUM(1,1)")
            self.assertEqual(sheet['C2'].data_type, 's')
            self.assertEqual(sheet['F2'].value, 60)
        finally:
            book.close()
        self.assertEqual(
            self.client.get('/api/reports/export/', {**query, 'employee_id': self.foreign.pk}).status_code, 403
        )
        self.assertEqual(self.client.get('/api/reports/export/', {**query, 'end': 'bad'}).status_code, 400)
        self.assertEqual(self.client.get('/api/reports/export/', {**query, 'file_type': 'pdf'}).status_code, 400)

    @patch('activity.management.commands.run_backup_scheduler.close_old_connections')
    def test_retention_is_opt_in_and_runs_only_after_successful_backup(self, _close):
        from django.core.management import call_command, CommandError
        from unittest.mock import patch

        policy = current_settings()
        with patch('activity.management.commands.run_backup_scheduler.call_command') as run:
            call_command('run_backup_scheduler', once=True)
            self.assertEqual([call.args[0] for call in run.call_args_list], ['backup_cycle'])
        policy.automatic_retention = True
        policy.activity_retention_days = 14
        policy.save()
        with patch('activity.management.commands.run_backup_scheduler.call_command') as run:
            call_command('run_backup_scheduler', once=True)
            self.assertEqual([call.args[0] for call in run.call_args_list], ['backup_cycle', 'cleanup_activity'])
            self.assertEqual(run.call_args.kwargs['days'], 14)
        with patch(
            'activity.management.commands.run_backup_scheduler.call_command', side_effect=CommandError('backup failed')
        ) as run:
            with self.assertRaises(CommandError):
                call_command('run_backup_scheduler', once=True)
            self.assertEqual(run.call_count, 1)

    def test_retention_safety_backup_precedes_deletion_and_new_arrivals_survive(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from django.test import override_settings
        from django.core.management import call_command

        now = timezone.now()
        old = CameraPresence.objects.create(
            employee=self.worker, timestamp=now - timedelta(days=100), present=True, confidence=0.8
        )
        late = []
        with TemporaryDirectory() as directory, override_settings(BASE_DIR=Path(directory)):
            (Path(directory) / 'backups').mkdir()

            def backup(path):
                self.assertTrue(CameraPresence.objects.filter(pk=old.pk).exists())
                late.append(
                    CameraPresence.objects.create(
                        employee=self.worker, timestamp=now - timedelta(days=101), present=False, confidence=0
                    ).pk
                )
                return path

            with (
                patch('activity.backups.create_backup', side_effect=backup),
                patch('activity.backups.verify_backup') as verify,
            ):
                call_command('cleanup_activity', days=90, apply=True, backup=True, stdout=StringIO())
                verify.assert_called_once()
        self.assertFalse(CameraPresence.objects.filter(pk=old.pk).exists())
        self.assertTrue(CameraPresence.objects.filter(pk=late[0]).exists())

    def test_django_admin_changes_are_visible_in_the_same_audit_history(self):
        from django.contrib.admin import AdminSite
        from django.test import RequestFactory
        from .admin import CustomUserAdmin

        model_admin = CustomUserAdmin(User, AdminSite())
        request = RequestFactory().post('/admin/users/user/')
        request.user = self.admin
        self.worker.role = 'MANAGER'
        model_admin.save_model(request, self.worker, None, True)
        entry = AuditEntry.objects.get(resource='user', action='update')
        self.assertEqual(entry.changes['role'], {'before': 'EMPLOYEE', 'after': 'MANAGER'})
        password_request = RequestFactory().post('/admin/users/user/password/')
        password_request.user = self.admin
        model_admin.log_change(password_request, self.worker, 'Password changed.')
        self.assertTrue(AuditEntry.objects.filter(action='admin_change').exists())
