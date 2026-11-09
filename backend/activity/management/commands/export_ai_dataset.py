"""Write the labeled CSV the AI experiment reads (ai/experiment.py --data-kind real).

One row per person and day that has the person's own end-of-day rating (Бага / Дунд / Өндөр)
and computer activity. People appear only as a pseudonym derived from the server's secret key,
never by name or id. Features, each between 0 and 1:

  active_ratio           time not idle / all recorded computer time
  work_app_ratio         time in work programs / time not idle
  presence_ratio         camera "person present" samples / all camera samples (0 without camera)
  task_completion_ratio  tasks due that day and finished by its end / tasks due that day (the
                         score's T; 0 when nothing was due)
"""

import csv
from datetime import date, datetime, time, timedelta
import hashlib
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, Q, Sum
from django.utils import timezone

from activity.models import CameraPresence, ComputerActivity
from users.models import DailySelfRating
from workforce.models import Task

FIELDS = (
    'participant_id',
    'sample_id',
    'data_kind',
    'active_ratio',
    'work_app_ratio',
    'presence_ratio',
    'task_completion_ratio',
    'label',
)
LABELS = {'LOW': 'Low', 'MEDIUM': 'Medium', 'HIGH': 'High'}


def pseudonym(employee_id):
    return 'p-' + hashlib.sha256(f'{settings.SECRET_KEY}:ai:{employee_id}'.encode()).hexdigest()[:12]


def ratio(part, whole):
    return round(min(1.0, part / whole), 4) if whole else 0.0


def features(employee, day):
    """The four ratios for one person and day, or None without computer activity."""
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = start + timedelta(days=1)
    activity = ComputerActivity.objects.filter(employee=employee, started_at__gte=start, started_at__lt=end)
    totals = activity.aggregate(
        all=Sum('duration_seconds'),
        idle=Sum('duration_seconds', filter=Q(application__iexact='idle')),
        work=Sum(
            'duration_seconds', filter=Q(category=ComputerActivity.Category.WORK) & ~Q(application__iexact='idle')
        ),
    )
    recorded = totals['all'] or 0
    if not recorded:
        return None
    active = recorded - (totals['idle'] or 0)
    camera = CameraPresence.objects.filter(employee=employee, timestamp__gte=start, timestamp__lt=end).aggregate(
        samples=Count('pk'), present=Count('pk', filter=Q(present=True))
    )
    due = Task.objects.filter(employee=employee, due_date=day)
    finished = due.filter(status=Task.Status.DONE, completed_at__lt=end).count()
    return {
        'active_ratio': ratio(active, recorded),
        'work_app_ratio': ratio(totals['work'] or 0, active),
        'presence_ratio': ratio(camera['present'], camera['samples']),
        'task_completion_ratio': ratio(finished, due.count()),
        'has_camera': bool(camera['samples']),
    }


class Command(BaseCommand):
    help = 'Export the labeled, pseudonymous daily dataset for ai/experiment.py.'

    def add_arguments(self, parser):
        parser.add_argument('--out', required=True, type=Path)
        parser.add_argument('--since', type=date.fromisoformat)
        parser.add_argument('--until', type=date.fromisoformat)
        parser.add_argument('--require-camera', action='store_true', help='Skip days without camera samples.')

    def handle(self, *args, **options):
        ratings = DailySelfRating.objects.select_related('employee').order_by('date', 'employee_id')
        if options['since']:
            ratings = ratings.filter(date__gte=options['since'])
        if options['until']:
            ratings = ratings.filter(date__lte=options['until'])
        rows, skipped, without_camera = [], 0, 0
        for rating in ratings.iterator():
            values = features(rating.employee, rating.date)
            if values is None or (options['require_camera'] and not values['has_camera']):
                skipped += 1
                continue
            without_camera += not values.pop('has_camera')
            participant = pseudonym(rating.employee_id)
            rows.append(
                {
                    'participant_id': participant,
                    'sample_id': f'{participant}-{rating.date.isoformat()}',
                    'data_kind': 'real',
                    **values,
                    'label': LABELS[rating.label],
                }
            )
        out = options['out']
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        people = len({row['participant_id'] for row in rows})
        labels = {label: sum(row['label'] == label for row in rows) for label in LABELS.values()}
        self.stdout.write(
            f'{len(rows)} rows from {people} people; labels {labels}; {skipped} rated days skipped '
            f'(no computer activity{" or camera" if options["require_camera"] else ""}); '
            f'{without_camera} rows without camera (presence_ratio 0).'
        )
        missing = []
        if len(rows) < 30:
            missing.append(f'{30 - len(rows)} more rows')
        if people < 5:
            missing.append(f'{5 - people} more people')
        if any(count == 0 for count in labels.values()):
            missing.append('every label (Low, Medium, High) at least once')
        self.stdout.write(
            'Ready for: python ai/experiment.py --data-kind real --csv ' + str(out)
            if not missing
            else 'The experiment still needs ' + ', '.join(missing) + '.'
        )
