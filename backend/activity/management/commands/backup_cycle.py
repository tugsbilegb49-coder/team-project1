"""Daily backup, optional second copy, and retention of generated backups."""
from datetime import datetime, timezone as utc_timezone
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from activity.backups import create_backup, verify_backup

GENERATED=re.compile(r'^daily-\d{8}T\d{6}Z-[0-9a-f]{8}\.(sqlite3|dump)$')


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):
            value.update(block)
    return value.digest()


class Command(BaseCommand):
    help='Create at most one generated backup per local day; keep 7 by default. Optional existing second-copy directory.'

    def add_arguments(self, parser):
        parser.add_argument('--keep',type=int,default=settings.BACKUP_KEEP)
        parser.add_argument('--copy-dir',default=os.environ.get('BACKUP_COPY_DIR'))

    def handle(self,*args,**options):
        keep=options['keep']
        if keep<1:
            raise CommandError('--keep must be at least 1.')
        directory=settings.BASE_DIR/'backups'
        directory.mkdir(parents=True,exist_ok=True)
        files=sorted((p for p in directory.iterdir() if p.is_file() and not p.is_symlink() and GENERATED.fullmatch(p.name)),key=lambda p:p.stat().st_mtime,reverse=True)
        today=timezone.localdate()
        current=next((p for p in files if datetime.fromtimestamp(p.stat().st_mtime,timezone.get_current_timezone()).date()==today),None)
        if current is None:
            suffix='.sqlite3' if connections['default'].vendor=='sqlite' else '.dump'
            name=f"daily-{datetime.now(utc_timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}{suffix}"
            current=create_backup(directory/name)
            files.insert(0,current)
            self.stdout.write(f'Daily backup created: {current}')
        else:
            self.stdout.write(f'Daily backup already exists: {current}')
        verify_backup(current)
        if options.get('copy_dir'):
            target=Path(options['copy_dir']).expanduser().resolve()
            if not target.is_dir():
                raise CommandError('Copy directory must already exist (mount the backup disk first). No local backups pruned.')
            destination=target/current.name
            if destination.exists():
                if digest(destination)!=digest(current):
                    raise CommandError('Second-copy filename exists with different data; nothing overwritten or pruned.')
            else:
                temporary=target/('.backup-'+secrets.token_hex(8)+'.tmp')
                try:
                    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                    with os.fdopen(fd,'wb') as output,current.open('rb') as source:
                        shutil.copyfileobj(source,output)
                    if digest(temporary)!=digest(current):
                        raise CommandError('Second-copy checksum mismatch.')
                    os.replace(temporary,destination)
                finally:
                    temporary.unlink(missing_ok=True)
            self.stdout.write(f'Verified second copy: {destination}')
        if settings.ACTIVITY_RETENTION_AUTO:
            self.stdout.write(f'Applying {settings.ACTIVITY_RETENTION_DAYS}-day activity retention after verified backup.')
            call_command('cleanup_activity', days=settings.ACTIVITY_RETENTION_DAYS, apply=True,
                         stdout=self.stdout, stderr=self.stderr)
        for old in files[keep:]:
            old.unlink()
        self.stdout.write(f'Local generated backups retained: {min(len(files),keep)}. Custom files and external copies are not pruned.')
