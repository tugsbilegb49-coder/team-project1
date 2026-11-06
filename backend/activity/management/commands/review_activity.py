"""Preview legacy data issues; explicit apply only reclassifies aggregate apps."""
from datetime import timedelta
import math
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from activity.models import ComputerActivity, ActivityEvent
from activity.classification import category_for_application


class Command(BaseCommand):
    help = 'Review invalid/overlapping historical intervals. --apply reclassifies only aggregate-agent apps; never deletes rows.'

    def add_arguments(self, parser):
        parser.add_argument('--employee', type=int)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--limit', type=int, default=100, help='Maximum issue details printed; all rows are scanned.')

    def handle(self, *args, **options):
        if options['limit'] < 0:
            raise CommandError('--limit must be nonnegative.')
        issues=0
        candidates=[]
        now=timezone.now()
        for model,field in ((ComputerActivity,'started_at'),(ActivityEvent,'timestamp')):
            rows=model.objects.select_related('device').order_by('employee_id',field,'pk')
            if options.get('employee'):
                rows=rows.filter(employee_id=options['employee'])
            latest={}
            for row in rows.iterator():
                duration=row.duration_seconds
                reason=None
                try:
                    if not math.isfinite(duration) or not 0 < duration <= 3600:
                        raise ValueError('duration outside (0,3600]')
                    timestamp=getattr(row,field)
                    start,end=(timestamp,timestamp+timedelta(seconds=duration)) if model is ComputerActivity else (timestamp-timedelta(seconds=duration),timestamp)
                    if end > now:
                        reason='future interval'
                    if row.employee_id in latest and start < latest[row.employee_id] - timedelta(seconds=0 if model is ComputerActivity else .1):
                        reason='overlapping interval'
                    latest[row.employee_id]=max(end,latest.get(row.employee_id,end))
                except (ValueError,OverflowError):
                    reason='invalid duration/date range'
                if reason:
                    issues+=1
                    if issues<=options['limit']:
                        self.stdout.write(f'{model.__name__} id={row.pk} employee={row.employee_id}: {reason}')
                if model is ComputerActivity and row.device and row.device.platform == 'activity_agent' and row.device.name.startswith('activity-agent-') and row.application not in {'Idle','Unattributed activity'}:
                    category=category_for_application(row.application)
                    if category!=row.category:
                        candidates.append((row.pk,row.category,category))
        self.stdout.write(f'Issues: {issues}; aggregate category changes: {len(candidates)}.')
        if options['apply']:
            with transaction.atomic():
                updated=0
                for pk,old,new in candidates:
                    updated+=ComputerActivity.objects.filter(pk=pk,category=old).update(category=new)
            self.stdout.write(f'Reclassified {updated} aggregate rows. Invalid intervals unchanged; no rows deleted. Recalculate affected historical scores explicitly.')
        else:
            self.stdout.write('Preview only. Back up before --apply. Invalid intervals require manual review.')
