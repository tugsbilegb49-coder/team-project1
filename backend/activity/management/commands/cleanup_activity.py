from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max
from django.conf import settings
from django.utils import timezone
from activity.models import ActivityEvent, ComputerActivity, CameraPresence, WebsiteActivity


class Command(BaseCommand):
    help = 'Preview old activity deletion; --apply deletes only segments wholly older than the cutoff.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, help='Retention age; defaults to central monitoring settings (initially 90).'
        )
        parser.add_argument('--apply', action='store_true')
        parser.add_argument(
            '--backup',
            action='store_true',
            help='Create and verify a fresh bounded retention safety backup before deletion.',
        )

    def handle(self, *args, **options):
        if options['days'] is None:
            from users.operations import current_settings

            options['days'] = current_settings().activity_retention_days
        if options['days'] < 1:
            raise CommandError('--days must be at least 1.')
        cutoff = timezone.now() - timedelta(days=options['days'])
        with transaction.atomic():
            camera_max = ActivityEvent.objects.aggregate(pk=Max('pk'))['pk'] or 0
            presence_max = CameraPresence.objects.aggregate(pk=Max('pk'))['pk'] or 0
            website_max = WebsiteActivity.objects.aggregate(pk=Max('pk'))['pk'] or 0
            camera = ActivityEvent.objects.filter(timestamp__lt=cutoff, pk__lte=camera_max)
            presence = CameraPresence.objects.filter(timestamp__lt=cutoff, pk__lte=presence_max)
            website_ids = [
                pk
                for pk, start, duration in WebsiteActivity.objects.filter(started_at__lt=cutoff, pk__lte=website_max)
                .values_list('pk', 'started_at', 'duration_seconds')
                .iterator()
                if start + timedelta(seconds=duration) < cutoff
            ]
            # Old imported segments may span the cutoff, so inspect their END.
            ids = [
                pk
                for pk, start, duration in ComputerActivity.objects.filter(started_at__lt=cutoff)
                .values_list('pk', 'started_at', 'duration_seconds')
                .iterator()
                if start + timedelta(seconds=duration) < cutoff
            ]
            self.stdout.write(
                f'Cutoff {cutoff.isoformat()}: camera={camera.count()}, computer={len(ids)}, '
                f'presence={presence.count()}, website={len(website_ids)}'
            )
            if options['apply']:
                if options['backup'] and (ids or website_ids or camera.exists() or presence.exists()):
                    from activity.backups import create_backup, verify_backup
                    from django.db import connection
                    from datetime import datetime, timezone as utc
                    import secrets

                    suffix = 'sqlite3' if connection.vendor == 'sqlite' else 'dump'
                    name = f'retention-{datetime.now(utc.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}.{suffix}'
                    backup = create_backup(settings.BASE_DIR / 'backups' / name)
                    verify_backup(backup)
                    self.stdout.write(f'Retention safety backup verified: {backup}')
                camera.delete()
                presence.delete()
                for offset in range(0, len(ids), 500):
                    from users.monthly import archive_activity

                    rows = list(ComputerActivity.objects.select_for_update().filter(pk__in=ids[offset : offset + 500]))
                    archive_activity(rows)
                    ComputerActivity.objects.filter(pk__in=[row.pk for row in rows]).delete()
                for offset in range(0, len(website_ids), 500):
                    WebsiteActivity.objects.filter(pk__in=website_ids[offset : offset + 500]).delete()
                self.stdout.write('Activity deleted. Users, tasks, consent and stored scores retained.')
                if options['backup']:
                    import re

                    directory = settings.BASE_DIR / 'backups'
                    owned = re.compile(r'^retention-\d{8}T\d{6}Z-[0-9a-f]{8}\.(sqlite3|dump)$')
                    files = sorted(
                        (
                            path
                            for path in directory.glob('retention-*')
                            if path.is_file() and not path.is_symlink() and owned.fullmatch(path.name)
                        ),
                        key=lambda path: path.stat().st_mtime,
                        reverse=True,
                    )
                    for path in files[7:]:
                        path.unlink()
            else:
                self.stdout.write('Preview only; nothing deleted. Use --apply after creating a backup.')
