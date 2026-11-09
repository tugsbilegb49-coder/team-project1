"""Consistent SQLite and PostgreSQL backups; never print database credentials."""

from datetime import datetime, timezone
from contextlib import closing
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import time

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connections


def backup_path(output=None):
    if output:
        path = Path(output).expanduser().resolve()
    else:
        suffix = '.sqlite3' if connections['default'].vendor == 'sqlite' else '.dump'
        path = (
            settings.BASE_DIR
            / 'backups'
            / f'database-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}{suffix}'
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def pg_command(tool, *args):
    configured = os.environ.get('POSTGRES_BIN_DIR')
    executable = str(Path(configured) / tool) if configured else shutil.which(tool)
    if not executable:
        candidate = Path('/opt/homebrew/opt/postgresql@17/bin') / tool
        if candidate.is_file():
            executable = str(candidate)
    if not executable:
        raise CommandError(f'{tool} is required for PostgreSQL backup/restore.')
    db = connections['default'].settings_dict
    env = os.environ.copy()
    for field, key in [
        ('PASSWORD', 'PGPASSWORD'),
        ('HOST', 'PGHOST'),
        ('PORT', 'PGPORT'),
        ('USER', 'PGUSER'),
        ('NAME', 'PGDATABASE'),
    ]:
        if db.get(field):
            env[key] = str(db[field])
    env.setdefault('PGCONNECT_TIMEOUT', '10')
    try:
        subprocess.run([executable, *args], env=env, check=True, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise CommandError(f'{tool} timed out.') from exc
    except subprocess.CalledProcessError as exc:
        raise CommandError(
            f'{tool} failed (exit {exc.returncode}); database configuration and server version must match.'
        ) from exc


def sqlite_source(path):
    source = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise CommandError('SQLite backup failed integrity_check.')
        tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'django_migrations', 'users_user', 'workforce_task', 'activity_computeractivity'} <= tables:
            raise CommandError('This file is not a migrated WorkTrack backend database.')
        return source
    except Exception:
        source.close()
        raise


def copy_sqlite(source, target):
    deadline = time.monotonic() + 60

    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise CommandError('SQLite backup timed out; stop active writers and retry.')

    source.backup(target, pages=256, progress=progress, sleep=0.1)


def create_backup(output=None):
    connection = connections['default']
    if connection.vendor not in {'sqlite', 'postgresql'}:
        raise CommandError('Only SQLite and PostgreSQL backups are supported.')
    path = backup_path(output)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError as exc:
        raise CommandError('Backup already exists; choose a new output path.') from exc
    try:
        if connection.vendor == 'sqlite':
            # Use a dedicated connection: backup() includes committed WAL data.
            db = Path(connection.settings_dict['NAME']).resolve()
            if not db.is_file():
                raise CommandError('Source SQLite database does not exist.')
            source = sqlite_source(db)
            try:
                with closing(sqlite3.connect(path)) as target:
                    copy_sqlite(source, target)
            finally:
                source.close()
        else:
            pg_command('pg_dump', '--format=custom', '--no-owner', '--file', str(path))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def verify_backup(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise CommandError('Backup file does not exist.')
    vendor = connections['default'].vendor
    if vendor == 'sqlite':
        try:
            source = sqlite_source(path)
            source.close()
        except sqlite3.Error as exc:
            raise CommandError('Invalid SQLite backup.') from exc
    elif vendor == 'postgresql':
        pg_command('pg_restore', '--list', str(path))
    else:
        raise CommandError('Unsupported database engine.')


def restore_backup(path):
    path = Path(path).resolve()
    connection = connections['default']
    verify_backup(path)
    if connection.vendor == 'sqlite' and os.path.samefile(path, connection.settings_dict['NAME']):
        raise CommandError('Backup source cannot be the live database itself.')
    # Preserve the current database before any destructive work.
    safety = create_backup()
    connections.close_all()
    if connection.vendor == 'sqlite':
        source = sqlite_source(path)
        try:
            with closing(sqlite3.connect(connection.settings_dict['NAME'])) as target:
                copy_sqlite(source, target)
        finally:
            source.close()
    else:
        pg_command(
            'pg_restore',
            '--clean',
            '--if-exists',
            '--single-transaction',
            '--exit-on-error',
            '--no-owner',
            '--dbname',
            str(connection.settings_dict['NAME']),
            str(path),
        )
    return safety
