from datetime import timedelta
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from users.models import User, Device
from .models import ComputerActivity


class ReviewActivityTests(TestCase):
    def test_preview_then_reclassify_only_aggregate_rows(self):
        user = User.objects.create_user('historical-worker')
        device = Device.objects.create(employee=user, name='activity-agent-legacy', platform='activity_agent')
        now = timezone.now() - timedelta(seconds=60)
        old = ComputerActivity.objects.create(
            employee=user, device=device, started_at=now, duration_seconds=30, application='code.exe', category='OTHER'
        )
        primary = ComputerActivity.objects.create(
            employee=user,
            started_at=now - timedelta(minutes=1),
            duration_seconds=30,
            application='Code',
            category='OTHER',
        )
        out = StringIO()
        call_command('review_activity', stdout=out)
        old.refresh_from_db()
        self.assertEqual(old.category, 'OTHER')
        call_command('review_activity', apply=True, stdout=StringIO())
        old.refresh_from_db()
        primary.refresh_from_db()
        self.assertEqual(old.category, 'WORK')
        self.assertEqual(primary.category, 'OTHER')
        self.assertEqual(ComputerActivity.objects.count(), 2)

    def test_invalid_intervals_are_reported_not_deleted(self):
        user = User.objects.create_user('invalid-history')
        ComputerActivity.objects.create(
            employee=user, started_at=timezone.now(), duration_seconds=9999, application='Code'
        )
        output = StringIO()
        call_command('review_activity', apply=True, stdout=output)
        self.assertIn('invalid duration', output.getvalue())
        self.assertEqual(ComputerActivity.objects.count(), 1)


class BackupCycleTests(SimpleTestCase):
    def test_reuses_daily_backup_prunes_only_generated_and_verifies_second_copy(self):
        with TemporaryDirectory() as directory, TemporaryDirectory() as copy:
            root = Path(directory)
            backups = root / 'backups'
            backups.mkdir()
            for number in range(5):
                path = backups / f'daily-2026110{number}T000000Z-deadbeef.sqlite3'
                path.write_bytes(f'backup-{number}'.encode())
                moment = timezone.now().timestamp() - number * 86400
                os.utime(path, (moment, moment))
            custom = backups / 'my-manual-backup.sqlite3'
            custom.write_text('keep')
            with (
                override_settings(BASE_DIR=root),
                patch('activity.management.commands.backup_cycle.verify_backup'),
                patch('activity.management.commands.backup_cycle.create_backup') as create,
            ):
                call_command('backup_cycle', keep=2, copy_dir=copy, stdout=StringIO())
            create.assert_not_called()
            self.assertTrue(custom.exists())
            self.assertEqual(len(list(backups.glob('daily-*'))), 2)
            copied = list(Path(copy).iterdir())
            self.assertEqual(len(copied), 1)
            self.assertEqual(copied[0].read_bytes(), b'backup-0')
            if os.name != 'nt':  # Windows has no POSIX permission bits.
                self.assertEqual(copied[0].stat().st_mode & 0o777, 0o600)

    def test_unmounted_copy_destination_does_not_prune_local_history(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            backups = root / 'backups'
            backups.mkdir()
            for number in range(3):
                (backups / f'daily-2026110{number}T000000Z-deadbeef.sqlite3').write_bytes(b'backup')
            with override_settings(BASE_DIR=root), patch('activity.management.commands.backup_cycle.verify_backup'):
                with self.assertRaises(CommandError):
                    call_command('backup_cycle', keep=1, copy_dir=str(root / 'unmounted'), stdout=StringIO())
            self.assertEqual(len(list(backups.glob('daily-*'))), 3)
