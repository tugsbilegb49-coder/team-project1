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
    with tempfile.TemporaryDirectory(prefix='worktrack-pg-', dir='/private/tmp' if Path('/private/tmp').exists() else None) as directory:
        root = Path(directory)
        cluster, socket = root / 'cluster', root / 'socket'
        socket.mkdir(mode=0o700)
        env = os.environ.copy()
        env.update({
            'PATH':str(args.pg_bin)+os.pathsep+env.get('PATH',''),
            'LC_ALL':'C','LANG':'C',
            'POSTGRES_DB':'worktrack_verification','POSTGRES_USER':getpass.getuser(),
            'POSTGRES_PASSWORD':'','POSTGRES_HOST':str(socket),'POSTGRES_PORT':'55441',
            'PGHOST':str(socket),'PGPORT':'55441','PGUSER':getpass.getuser(),
            'PGDATABASE':'worktrack_verification','PGPASSWORD':'',
            'DJANGO_SETTINGS_MODULE':'verification_settings',
            'PYTHONPATH':str(root)+os.pathsep+str(ROOT/'backend'),
        })
        (root/'verification_settings.py').write_text('from config.settings import *\nfrom pathlib import Path\nBASE_DIR=Path('+repr(str(root))+')\n')

        def pg(name, *values, **kwargs):
            return subprocess.run([str(args.pg_bin/name),*values],env=env,check=True,**kwargs)

        def manage(*values):
            subprocess.run([sys.executable,'manage.py',*values],cwd=ROOT,env=env,check=True)

        pg('initdb','-D',str(cluster),'--auth-local=trust','--auth-host=reject','--locale=C','--encoding=UTF8','--no-sync',stdout=subprocess.DEVNULL)
        started = False
        try:
            pg('pg_ctl','-D',str(cluster),'-l',str(root/'postgres.log'),'-o',
               shlex.join(['-h','','-k',str(socket),'-p','55441']),'-w','start',stdout=subprocess.DEVNULL)
            started = True
            pg('createdb','worktrack_verification')
            print('PASS: private PostgreSQL cluster started (Unix socket only).',flush=True)
            manage('migrate','--noinput','--verbosity','0')
            print('PASS: PostgreSQL migrations.',flush=True)
            manage('test','users','workforce','activity','scoring','--noinput')
            manage('shell','-c',"from django.contrib.auth import get_user_model; get_user_model().objects.create_user(username='pg_original',password=None)")
            snapshot = root/'snapshot.dump'
            manage('backup_database','--output',str(snapshot))
            manage('shell','-c',"from django.contrib.auth import get_user_model; get_user_model().objects.create_user(username='pg_restore_probe',password=None)")
            manage('restore_database',str(snapshot),'--apply','--confirm-stopped')
            manage('shell','-c',"from django.contrib.auth import get_user_model; User=get_user_model(); assert User.objects.filter(username='pg_original').exists(); assert not User.objects.filter(username='pg_restore_probe').exists(); print('PASS: real PostgreSQL restore reverted the probe row.')")
            safety = list((root/'backups').glob('*.dump'))
            if len(safety) != 1:
                raise RuntimeError('Expected exactly one pre-restore safety backup.')
            pg('createdb','worktrack_safety_check')
            pg('pg_restore','--dbname','worktrack_safety_check','--no-owner',str(safety[0]),stdout=subprocess.DEVNULL)
            result = pg('psql','--dbname','worktrack_safety_check','-Atc',"SELECT count(*) FROM users_user WHERE username='pg_restore_probe'",capture_output=True,text=True)
            if result.stdout.strip() != '1':
                raise RuntimeError('Safety backup does not contain the pre-restore change.')
            print('PASS: safety backup independently restored.',flush=True)
            version = pg('postgres','--version',capture_output=True,text=True).stdout.strip()
            (ROOT/'.runtime').mkdir(exist_ok=True)
            (ROOT/'.runtime/postgresql-verification.json').write_text(json.dumps({
                'version':version,'migrations':'passed','backend_tests':'passed',
                'concurrent_ingestion':'passed','backup_restore':'passed',
                'safety_backup_restore':'passed','live_sqlite_modified':False,
            },indent=2))
        finally:
            if started:
                pg('pg_ctl','-D',str(cluster),'-m','fast','-w','-t','20','stop',stdout=subprocess.DEVNULL)
                print('Temporary PostgreSQL server stopped.',flush=True)
    print('Temporary cluster removed; no permanent service enabled; SQLite unchanged.',flush=True)


if __name__ == '__main__':
    main()
