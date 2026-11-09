#!/usr/bin/env python3
"""Run isolated real PostgreSQL tests and a backup/restore drill on macOS/Linux."""

import argparse
import getpass
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import socket as socketlib
import time
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
import tempfile

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    located = shutil.which('pg_ctl')
    default_bin = Path(located).parent if located else Path('/opt/homebrew/opt/postgresql@17/bin')
    parser.add_argument('--pg-bin', type=Path, default=default_bin)
    args = parser.parse_args()
    if os.name == 'nt':
        parser.error('This isolated Unix-socket verifier supports macOS/Linux.')
    if not (args.pg_bin / 'initdb').exists():
        parser.error('PostgreSQL tools missing; pass --pg-bin /path/to/postgresql/bin.')
    with tempfile.TemporaryDirectory(
        prefix='worktrack-pg-', dir='/private/tmp' if Path('/private/tmp').exists() else None
    ) as directory:
        root = Path(directory)
        cluster, socket = root / 'cluster', root / 'socket'
        socket.mkdir(mode=0o700)
        env = os.environ.copy()
        env.update(
            {
                'PATH': str(args.pg_bin) + os.pathsep + env.get('PATH', ''),
                'LC_ALL': 'C',
                'LANG': 'C',
                'DJANGO_CACHE_BACKEND': 'database',
                'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,testserver',
                'DJANGO_SECURE_SSL_REDIRECT': 'false',
                'POSTGRES_DB': 'worktrack_verification',
                'POSTGRES_USER': getpass.getuser(),
                'POSTGRES_PASSWORD': '',
                'POSTGRES_HOST': str(socket),
                'POSTGRES_PORT': '55441',
                'PGHOST': str(socket),
                'PGPORT': '55441',
                'PGUSER': getpass.getuser(),
                'PGDATABASE': 'worktrack_verification',
                'PGPASSWORD': '',
                'DJANGO_SETTINGS_MODULE': 'verification_settings',
                'PYTHONPATH': str(root) + os.pathsep + str(ROOT / 'backend'),
            }
        )
        (root / 'verification_settings.py').write_text(
            'from config.settings import *\nfrom pathlib import Path\nBASE_DIR=Path(' + repr(str(root)) + ')\n'
        )

        def pg(name, *values, **kwargs):
            return subprocess.run([str(args.pg_bin / name), *values], env=env, check=True, **kwargs)

        def manage(*values):
            subprocess.run([sys.executable, 'manage.py', *values], cwd=ROOT, env=env, check=True)

        pg(
            'initdb',
            '-D',
            str(cluster),
            '--auth-local=trust',
            '--auth-host=reject',
            '--locale=C',
            '--encoding=UTF8',
            '--no-sync',
            stdout=subprocess.DEVNULL,
        )
        started = False
        try:
            pg(
                'pg_ctl',
                '-D',
                str(cluster),
                '-l',
                str(root / 'postgres.log'),
                '-o',
                shlex.join(['-h', '', '-k', str(socket), '-p', '55441']),
                '-w',
                'start',
                stdout=subprocess.DEVNULL,
            )
            started = True
            pg('createdb', 'worktrack_verification')
            print('PASS: private PostgreSQL cluster started (Unix socket only).', flush=True)
            manage('migrate', '--noinput', '--verbosity', '0')
            manage('createcachetable')
            print('PASS: PostgreSQL migrations.', flush=True)
            manage(
                'shell',
                '-c',
                "from django.core.cache import cache; cache.set('verification-cross-process','shared',60)",
            )
            manage(
                'shell',
                '-c',
                "from django.core.cache import cache; assert cache.get('verification-cross-process')=='shared'; cache.delete('verification-cross-process'); print('PASS: shared cache read across independent processes.')",
            )
            with socketlib.socket() as reservation:
                reservation.bind(('127.0.0.1', 0))
                http_port = reservation.getsockname()[1]
            with (root / 'gunicorn.log').open('w') as log:
                web = subprocess.Popen(
                    [
                        sys.executable,
                        '-m',
                        'gunicorn',
                        'config.wsgi:application',
                        '--bind',
                        f'127.0.0.1:{http_port}',
                        '--workers',
                        '2',
                    ],
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + 15
                    url = f'http://127.0.0.1:{http_port}'
                    while True:
                        try:
                            with urlopen(url + '/api/health/', timeout=1) as response:
                                if response.status == 200:
                                    break
                        except (URLError, TimeoutError):
                            if web.poll() is not None or time.monotonic() > deadline:
                                raise RuntimeError('Gunicorn readiness failed; see temporary log.')
                            time.sleep(0.1)
                    statuses = []
                    for _ in range(11):
                        request = Request(
                            url + '/api/auth/login/',
                            data=json.dumps(
                                {'username': 'nonexistent-verification-user', 'password': 'invalid'}
                            ).encode(),
                            headers={'Content-Type': 'application/json'},
                        )
                        try:
                            with urlopen(request, timeout=5) as response:
                                statuses.append(response.status)
                        except HTTPError as exc:
                            statuses.append(exc.code)
                            exc.close()
                    if statuses[:10] != [401] * 10 or statuses[10] != 429:
                        raise RuntimeError(f'Multi-worker login throttle failed: {statuses}')
                    print('PASS: two-worker Gunicorn readiness and shared login throttle.', flush=True)
                finally:
                    web.terminate()
                    try:
                        web.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        web.kill()
                        web.wait()

            manage('test', 'users', 'workforce', 'activity', 'scoring', '--noinput')
            manage(
                'shell',
                '-c',
                "from django.contrib.auth import get_user_model; get_user_model().objects.create_user(username='pg_original',password=None)",
            )
            manage(
                'shell',
                '-c',
                "from datetime import timedelta; from django.utils import timezone; from users.models import User; from activity.models import CameraPresence; CameraPresence.objects.create(employee=User.objects.get(username='pg_original'),timestamp=timezone.now()-timedelta(days=100),present=True,confidence=.8)",
            )
            manage('cleanup_activity', '--days', '90', '--apply', '--backup')
            manage(
                'shell', '-c', 'from activity.models import CameraPresence; assert not CameraPresence.objects.exists()'
            )
            retention = list((root / 'backups').glob('retention-*.dump'))
            if len(retention) != 1:
                raise RuntimeError('Expected one fresh pre-retention backup.')
            pg('createdb', 'worktrack_retention_check')
            pg(
                'pg_restore',
                '--dbname',
                'worktrack_retention_check',
                '--no-owner',
                str(retention[0]),
                stdout=subprocess.DEVNULL,
            )
            retained = pg(
                'psql',
                '--dbname',
                'worktrack_retention_check',
                '-Atc',
                'SELECT count(*) FROM activity_camerapresence',
                capture_output=True,
                text=True,
            )
            if retained.stdout.strip() != '1':
                raise RuntimeError('Retention safety backup did not preserve the deleted row.')
            print(
                'PASS: activity retention deleted only after a fresh independently restored safety backup.', flush=True
            )
            copy_dir = root / 'second-copy'
            copy_dir.mkdir(mode=0o700)
            manage('backup_cycle', '--copy-dir', str(copy_dir), '--keep', '2')
            manage('backup_cycle', '--copy-dir', str(copy_dir), '--keep', '2')
            if len(list((root / 'backups').glob('daily-*.dump'))) != 1 or len(list(copy_dir.glob('daily-*.dump'))) != 1:
                raise RuntimeError('Daily backup deduplication or verified copy failed.')
            print('PASS: daily PostgreSQL backup and verified second copy.', flush=True)
            snapshot = root / 'snapshot.dump'
            manage('backup_database', '--output', str(snapshot))
            manage(
                'shell',
                '-c',
                "from django.contrib.auth import get_user_model; get_user_model().objects.create_user(username='pg_restore_probe',password=None)",
            )
            manage('restore_database', str(snapshot), '--apply', '--confirm-stopped')
            manage(
                'shell',
                '-c',
                "from django.contrib.auth import get_user_model; User=get_user_model(); assert User.objects.filter(username='pg_original').exists(); assert not User.objects.filter(username='pg_restore_probe').exists(); print('PASS: real PostgreSQL restore reverted the probe row.')",
            )
            safety = list((root / 'backups').glob('database-*.dump'))
            if len(safety) != 1:
                raise RuntimeError('Expected exactly one pre-restore safety backup.')
            pg('createdb', 'worktrack_safety_check')
            pg(
                'pg_restore',
                '--dbname',
                'worktrack_safety_check',
                '--no-owner',
                str(safety[0]),
                stdout=subprocess.DEVNULL,
            )
            result = pg(
                'psql',
                '--dbname',
                'worktrack_safety_check',
                '-Atc',
                "SELECT count(*) FROM users_user WHERE username='pg_restore_probe'",
                capture_output=True,
                text=True,
            )
            if result.stdout.strip() != '1':
                raise RuntimeError('Safety backup does not contain the pre-restore change.')
            print('PASS: safety backup independently restored.', flush=True)
            version = pg('postgres', '--version', capture_output=True, text=True).stdout.strip()
            (ROOT / '.runtime').mkdir(exist_ok=True)
            (ROOT / '.runtime/postgresql-verification.json').write_text(
                json.dumps(
                    {
                        'version': version,
                        'migrations': 'passed',
                        'backend_tests': 'passed',
                        'concurrent_ingestion': 'passed',
                        'shared_cache': 'passed',
                        'gunicorn_multi_worker': 'passed',
                        'backup_restore': 'passed',
                        'safety_backup_restore': 'passed',
                        'live_sqlite_modified': False,
                        'retention_safety_backup_restore': 'passed',
                    },
                    indent=2,
                )
            )
        finally:
            if started:
                pg('pg_ctl', '-D', str(cluster), '-m', 'fast', '-w', '-t', '20', 'stop', stdout=subprocess.DEVNULL)
                print('Temporary PostgreSQL server stopped.', flush=True)
    print('Temporary cluster removed; no permanent service enabled; SQLite unchanged.', flush=True)


if __name__ == '__main__':
    main()
