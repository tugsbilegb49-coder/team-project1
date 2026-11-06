from contextlib import closing
from datetime import timedelta
from io import StringIO
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from .backups import create_backup, restore_backup, verify_backup
from .models import ActivityEvent, ComputerActivity
from users.models import User


class SQLiteBackupTests(SimpleTestCase):
    def setUp(self):
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.live=self.root/'live.sqlite3'
        with closing(sqlite3.connect(self.live)) as db:
            for name in ('django_migrations','users_user','workforce_task','activity_computeractivity'):
                db.execute(f'CREATE TABLE {name} (id INTEGER PRIMARY KEY, name TEXT)')
            db.execute("INSERT INTO users_user VALUES (1,'original')")
            db.commit()
        connection=MagicMock(vendor='sqlite')
        connection.settings_dict={'NAME':str(self.live)}
        self.connections=MagicMock()
        self.connections.__getitem__.return_value=connection
        self.patcher=patch('activity.backups.connections',self.connections)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.settings_override=override_settings(BASE_DIR=self.root)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def test_backup_restores_rows_and_preserves_pre_restore_database(self):
        backup=create_backup(self.root/'copy.sqlite3')
        self.assertEqual(backup.stat().st_mode & 0o777,0o600)
        with closing(sqlite3.connect(self.live)) as db:
            db.execute("UPDATE users_user SET name='changed'")
            db.commit()
        safety=restore_backup(backup)
        with closing(sqlite3.connect(self.live)) as db:
            self.assertEqual(db.execute('SELECT name FROM users_user').fetchone()[0],'original')
        with closing(sqlite3.connect(safety)) as db:
            self.assertEqual(db.execute('SELECT name FROM users_user').fetchone()[0],'changed')

    def test_existing_output_is_not_overwritten(self):
        path=self.root/'existing.sqlite3'
        path.write_text('keep me')
        with self.assertRaises(CommandError):
            create_backup(path)
        self.assertEqual(path.read_text(),'keep me')

    def test_invalid_backup_and_restore_without_confirmation_do_not_change_live_db(self):
        invalid=self.root/'invalid.sqlite3'
        invalid.write_text('not sqlite')
        with self.assertRaises(CommandError):
            verify_backup(invalid)
        backup=create_backup(self.root/'valid.sqlite3')
        out=StringIO()
        call_command('restore_database',str(backup),stdout=out)
        self.assertIn('database unchanged',out.getvalue())
        with self.assertRaises(CommandError):
            call_command('restore_database',str(backup),apply=True,stdout=StringIO())
        with self.assertRaises(CommandError):
            restore_backup(self.live)

    def test_wal_committed_rows_are_included_in_online_backup(self):
        with closing(sqlite3.connect(self.live)) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute("INSERT INTO users_user VALUES (2,'WAL data')")
            writer.commit()
            backup=create_backup(self.root/'wal-copy.sqlite3')
            with closing(sqlite3.connect(backup)) as reader:
                self.assertEqual(reader.execute('SELECT COUNT(*) FROM users_user').fetchone()[0],2)


class ActivityRetentionTests(TestCase):
    def test_preview_then_apply_preserves_recent_crossing_intervals_and_scores(self):
        user=User.objects.create_user('retention-worker')
        now=timezone.now()
        cutoff=now-timedelta(days=90)
        old=ComputerActivity.objects.create(employee=user,started_at=cutoff-timedelta(seconds=100),duration_seconds=30,application='Old')
        crossing=ComputerActivity.objects.create(employee=user,started_at=cutoff-timedelta(seconds=10),duration_seconds=30,application='Crossing')
        recent=ComputerActivity.objects.create(employee=user,started_at=now-timedelta(seconds=30),duration_seconds=30,application='Recent')
        camera=ActivityEvent.objects.create(employee=user,timestamp=cutoff-timedelta(seconds=1),duration_seconds=30,state='WORKING')
        from scoring.models import ProductivityScore
        score=ProductivityScore.objects.create(employee=user,date=(cutoff-timedelta(days=1)).date(),task_completion=0,quality=0,deadline_completion=0,work_process=0,score=0,category='LOW')
        with patch('activity.management.commands.cleanup_activity.timezone.now',return_value=now):
            call_command('cleanup_activity',stdout=StringIO())
            self.assertTrue(ComputerActivity.objects.filter(pk=old.pk).exists())
            call_command('cleanup_activity',apply=True,stdout=StringIO())
        self.assertFalse(ComputerActivity.objects.filter(pk=old.pk).exists())
        self.assertFalse(ActivityEvent.objects.filter(pk=camera.pk).exists())
        self.assertEqual(set(ComputerActivity.objects.values_list('pk',flat=True)),{crossing.pk,recent.pk})
        self.assertTrue(ProductivityScore.objects.filter(pk=score.pk).exists())
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_retention_must_be_positive(self):
        with self.assertRaises(CommandError):
            call_command('cleanup_activity',days=0,stdout=StringIO())


class PostgresBackupCommandTests(SimpleTestCase):
    def test_password_is_only_in_environment_not_command_arguments(self):
        from activity.backups import pg_command
        connections=MagicMock()
        connections.__getitem__.return_value.settings_dict={'NAME':'testdb','USER':'worker','PASSWORD':'private-value','HOST':'localhost','PORT':'5432'}
        with patch('activity.backups.connections',connections), patch('activity.backups.shutil.which',return_value='/bin/pg_dump'), patch('activity.backups.subprocess.run') as run:
            pg_command('pg_dump','--format=custom')
        self.assertNotIn('private-value',str(run.call_args.args))
        self.assertEqual(run.call_args.kwargs['env']['PGPASSWORD'],'private-value')
