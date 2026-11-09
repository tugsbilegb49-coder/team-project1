"""Daily backup, optional second copy, and retention of generated backups."""

from datetime import datetime, timezone as utc_timezone
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
from django.conf import settings
from django.db import connections
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from activity.backup_status import copy_dir_setting, write_status
from activity.backups import create_backup, verify_backup

GENERATED = re.compile(r'^daily-\d{8}T\d{6}Z-[0-9a-f]{8}\.(sqlite3|dump)$')


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.digest()


class Command(BaseCommand):
    help = (
        'Create at most one generated backup per local day; keep 7 by default. Optional existing second-copy directory.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--keep', type=int, default=os.environ.get('BACKUP_KEEP', '7'))
        parser.add_argument(
            '--copy-dir', help='Second copy; default BACKUP_COPY_DIR, then the folder set on the admin page.'
        )
        parser.add_argument('--copy-keep', type=int, default=os.environ.get('BACKUP_COPY_KEEP', '30'))

    def handle(self, *args, **options):
        copy_dir = options.get('copy_dir') or copy_dir_setting()[0]
        try:
            current, copied = self.cycle(options, copy_dir)
        except Exception as exc:
            write_status(error=str(exc) or exc.__class__.__name__, copy_dir=copy_dir or '')
            raise
        now = timezone.now().isoformat()
        write_status(
            error='',
            last_success_at=now,
            last_backup=current.name,
            copy_dir=copy_dir or '',
            **({'last_copy_at': now} if copied else {}),
        )

    def cycle(self, options, copy_dir):
        keep, copy_keep = options['keep'], options.get('copy_keep', 30)
        if keep < 1 or copy_keep < 1:
            raise CommandError('--keep and --copy-keep must be at least 1.')
        directory = settings.BASE_DIR / 'backups'
        directory.mkdir(parents=True, exist_ok=True)
        files = sorted(
            (p for p in directory.iterdir() if p.is_file() and not p.is_symlink() and GENERATED.fullmatch(p.name)),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        today = timezone.localdate()
        current = next(
            (
                p
                for p in files
                if datetime.fromtimestamp(p.stat().st_mtime, timezone.get_current_timezone()).date() == today
            ),
            None,
        )
        if current is None:
            suffix = '.sqlite3' if connections['default'].vendor == 'sqlite' else '.dump'
            name = f'daily-{datetime.now(utc_timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}{suffix}'
            current = create_backup(directory / name)
            files.insert(0, current)
            self.stdout.write(f'Daily backup created: {current}')
        else:
            self.stdout.write(f'Daily backup already exists: {current}')
        verify_backup(current)
        copied = False
        if copy_dir:
            target = Path(copy_dir).expanduser().resolve()
            if not target.is_dir():
                raise CommandError(
                    f'Хоёр дахь хуулбарын хавтас олдсонгүй: {target}. USB диск/сүлжээний хавтсаа холбоно уу. '
                    'Локал backup-ийг устгаагүй.'
                )
            destination = target / current.name
            if destination.exists():
                if digest(destination) != digest(current):
                    raise CommandError('Хоёр дахь хавтсанд ижил нэртэй өөр файл байна; юу ч дарж бичээгүй, устгаагүй.')
            else:
                temporary = target / ('.backup-' + secrets.token_hex(8) + '.tmp')
                try:
                    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    with os.fdopen(fd, 'wb') as output, current.open('rb') as source:
                        shutil.copyfileobj(source, output)
                    if digest(temporary) != digest(current):
                        raise CommandError('Хоёр дахь хуулбар эх файлтай таарсангүй (checksum).')
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
            self.stdout.write(f'Verified second copy: {destination}')
            copied = True
            copies = sorted(
                (p for p in target.iterdir() if p.is_file() and not p.is_symlink() and GENERATED.fullmatch(p.name)),
                key=lambda p: p.name,  # The names start with the UTC time they were made.
                reverse=True,
            )
            for old in copies[copy_keep:]:
                old.unlink()
        for old in files[keep:]:
            old.unlink()
        self.stdout.write(
            f'Local generated backups retained: {min(len(files), keep)}. Only generated copies are pruned elsewhere.'
        )
        return current, copied
