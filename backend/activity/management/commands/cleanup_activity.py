from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from activity.models import ActivityEvent, ComputerActivity


class Command(BaseCommand):
    help = 'Preview old activity deletion; --apply deletes only segments wholly older than the cutoff.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90, help='Retention age in days; minimum 1, default 90.')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        if options['days'] < 1:
            raise CommandError('--days must be at least 1.')
        cutoff = timezone.now() - timedelta(days=options['days'])
        with transaction.atomic():
            camera = ActivityEvent.objects.filter(timestamp__lt=cutoff)
            # Old imported segments may span the cutoff, so inspect their END.
            ids = [pk for pk,start,duration in ComputerActivity.objects.filter(started_at__lt=cutoff)
                .values_list('pk','started_at','duration_seconds').iterator()
                if start + timedelta(seconds=duration) < cutoff]
            self.stdout.write(f'Cutoff {cutoff.isoformat()}: camera={camera.count()}, computer={len(ids)}')
            if options['apply']:
                camera.delete()
                for offset in range(0,len(ids),500):
                    ComputerActivity.objects.filter(pk__in=ids[offset:offset+500]).delete()
                self.stdout.write('Activity deleted. Users, tasks, consent and stored scores retained.')
            else:
                self.stdout.write('Preview only; nothing deleted. Use --apply after creating a backup.')
