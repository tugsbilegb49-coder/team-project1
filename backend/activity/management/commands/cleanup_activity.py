from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from activity.models import ActivityEvent, ComputerActivity, WebsiteActivity
from scoring.models import ProductivityScore


class Command(BaseCommand):
    help = 'Preview retention cleanup; --apply deletes only activity segments wholly older than the cutoff.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=settings.ACTIVITY_RETENTION_DAYS,
                            help='Retention age in days; minimum 1; defaults to ACTIVITY_RETENTION_DAYS (90).')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        if options['days'] < 1:
            raise CommandError('--days must be at least 1.')
        cutoff = timezone.now() - timedelta(days=options['days'])
        score_cutoff = timezone.localdate() - timedelta(days=options['days'])
        with transaction.atomic():
            camera = ActivityEvent.objects.filter(timestamp__lt=cutoff)
            # Old imported segments may span the cutoff, so inspect their END.
            ids = [pk for pk,start,duration in ComputerActivity.objects.filter(started_at__lt=cutoff)
                .values_list('pk','started_at','duration_seconds').iterator()
                if start + timedelta(seconds=duration) < cutoff]
            website_ids = [pk for pk,start,duration in WebsiteActivity.objects.filter(started_at__lt=cutoff)
                .values_list('pk','started_at','duration_seconds').iterator()
                if start + timedelta(seconds=duration) < cutoff]
            scores = ProductivityScore.objects.filter(date__lt=score_cutoff)
            self.stdout.write(f'Cutoff {cutoff.isoformat()}: camera={camera.count()}, computer={len(ids)}, website={len(website_ids)}, scores={scores.count()}')
            if options['apply']:
                camera.delete()
                for offset in range(0,len(ids),500):
                    ComputerActivity.objects.filter(pk__in=ids[offset:offset+500]).delete()
                for offset in range(0,len(website_ids),500):
                    WebsiteActivity.objects.filter(pk__in=website_ids[offset:offset+500]).delete()
                scores.delete()
                self.stdout.write('Old activity and derived scores deleted. Users, tasks, consent and audit records retained.')
            else:
                self.stdout.write('Preview only; nothing deleted. Use --apply after creating a backup.')
