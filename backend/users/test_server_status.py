from datetime import timedelta
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AuditEntry, User


class ServerStatusTests(TestCase):
    def setUp(self):
        cache.clear()
        self.folder = TemporaryDirectory()
        self.root = Path(self.folder.name)
        (self.root / 'backups').mkdir()
        self.settings = override_settings(BASE_DIR=self.root)
        self.settings.enable()
        os.environ.pop('BACKUP_COPY_DIR', None)
        self.admin = User.objects.create_user('server-admin', role='ADMIN')
        self.worker = User.objects.create_user('server-worker')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def tearDown(self):
        self.settings.disable()
        self.folder.cleanup()

    def cycle(self, **options):
        backup = self.root / 'backups' / 'daily-20261107T000000Z-deadbeef.sqlite3'

        def create(path):
            backup.write_bytes(b'data')
            return backup

        with (
            patch('activity.management.commands.backup_cycle.verify_backup'),
            patch('activity.management.commands.backup_cycle.create_backup', side_effect=create),
        ):
            call_command('backup_cycle', stdout=StringIO(), **options)

    def test_admin_sets_a_second_folder_and_the_daily_backup_is_copied_there(self):
        copy = self.root / 'usb'
        copy.mkdir()
        self.assertEqual(
            self.client.patch('/api/server-status/', {'backup_copy_dir': 'relative/path'}).status_code, 400
        )
        self.assertEqual(
            self.client.patch('/api/server-status/', {'backup_copy_dir': str(self.root / 'missing')}).status_code, 400
        )
        response = self.client.patch('/api/server-status/', {'backup_copy_dir': str(copy)}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['backup']['copy_dir_source'], 'settings')
        self.cycle()
        self.assertEqual([p.name for p in copy.iterdir()], ['daily-20261107T000000Z-deadbeef.sqlite3'])
        backup = self.client.get('/api/server-status/').data['backup']
        self.assertEqual(backup['problems'], [])
        self.assertEqual(backup['status']['error'], '')
        self.assertIsNotNone(backup['status']['last_copy_at'])
        self.assertTrue(AuditEntry.objects.filter(resource='backup', action='configure').exists())

    def test_a_failed_copy_is_shown_to_admins_only(self):
        self.client.patch('/api/server-status/', {'backup_copy_dir': str(self.root)}, format='json')
        with self.assertRaises(Exception):
            self.cycle(copy_dir=str(self.root / 'unplugged'))
        alerts = self.client.get('/api/notifications/').data['items']
        self.assertEqual(alerts[0]['kind'], 'backup_failed')
        self.assertIn('unplugged', alerts[0]['message'])
        self.client.force_authenticate(self.worker)
        self.assertNotIn('backup_failed', [row['kind'] for row in self.client.get('/api/notifications/').data['items']])
        self.assertEqual(self.client.get('/api/server-status/').status_code, 403)

    def test_an_old_last_backup_is_reported_as_stale(self):
        old = (timezone.now() - timedelta(hours=40)).isoformat()
        (self.root / 'backups' / 'status.json').write_text(json.dumps({'last_success_at': old, 'error': ''}))
        self.assertEqual(self.client.get('/api/server-status/').data['backup']['problems'], ['backup_stale'])
        self.cycle()
        self.assertEqual(self.client.get('/api/server-status/').data['backup']['problems'], [])

    def test_the_server_environment_controls_the_folder_when_set(self):
        with patch.dict(os.environ, {'BACKUP_COPY_DIR': str(self.root)}):
            data = self.client.get('/api/server-status/').data['backup']
            self.assertEqual((data['copy_dir'], data['copy_dir_source']), (str(self.root), 'environment'))
            self.assertEqual(self.client.patch('/api/server-status/', {'backup_copy_dir': ''}).status_code, 409)

    def test_old_copies_beyond_the_limit_are_pruned_but_other_files_stay(self):
        copy = self.root / 'usb'
        copy.mkdir()
        for day in range(1, 5):
            (copy / f'daily-2026110{day}T000000Z-deadbeef.sqlite3').write_bytes(b'old')
        (copy / 'notes.txt').write_text('mine')
        self.cycle(copy_dir=str(copy), copy_keep=2)
        self.assertEqual(
            sorted(p.name for p in copy.iterdir()),
            ['daily-20261104T000000Z-deadbeef.sqlite3', 'daily-20261107T000000Z-deadbeef.sqlite3', 'notes.txt'],
        )
