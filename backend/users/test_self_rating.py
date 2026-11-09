import csv
from datetime import datetime, time, timedelta
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from activity.models import CameraPresence, ComputerActivity
from workforce.models import Task
from .models import DailySelfRating, User

sys.path.insert(0, str(Path(settings.BASE_DIR).parent))  # The repository root, for ai/.
from ai.experiment import FIELDS, validate_rows  # noqa: E402


class SelfRatingTests(TestCase):
    def setUp(self):
        self.worker = User.objects.create_user('rating-worker')
        self.client = APIClient()
        self.client.force_authenticate(self.worker)

    def test_today_is_rated_once_and_can_be_changed(self):
        self.assertIsNone(self.client.get('/api/me/self-rating/').data['label'])
        self.assertEqual(self.client.put('/api/me/self-rating/', {'label': 'MEDIUM'}, format='json').status_code, 200)
        self.assertEqual(self.client.put('/api/me/self-rating/', {'label': 'HIGH'}, format='json').status_code, 200)
        self.assertEqual(self.client.get('/api/me/self-rating/').data['label'], 'HIGH')
        self.assertEqual(DailySelfRating.objects.get().date, timezone.localdate())
        self.assertEqual(self.client.put('/api/me/self-rating/', {'label': 'GREAT'}, format='json').status_code, 400)
        self.assertEqual(APIClient().get('/api/me/self-rating/').status_code, 401)


class ExportTests(TestCase):
    def day_of(self, person, day, work, other, idle, present=None, due_done=None, label='MEDIUM', rate=True):
        start = timezone.make_aware(datetime.combine(day, time(9)))
        for offset, (application, category, seconds) in enumerate(
            [('Code', 'WORK', work), ('Safari', 'BROWSER', other), ('Idle', 'OTHER', idle)]
        ):
            if seconds:
                ComputerActivity.objects.create(
                    employee=person,
                    started_at=start + timedelta(hours=offset),
                    duration_seconds=seconds,
                    application=application,
                    category=category,
                )
        for index, value in enumerate(present or []):
            CameraPresence.objects.create(
                employee=person, timestamp=start + timedelta(minutes=index), present=value, confidence=0.9
            )
        if due_done is not None:
            Task.objects.create(
                employee=person,
                title='due',
                due_date=day,
                status=Task.Status.DONE if due_done else Task.Status.TODO,
                completed_at=start if due_done else None,
                quality_score=80 if due_done else None,
            )
        if rate:
            DailySelfRating.objects.create(employee=person, date=day, label=label)

    def test_one_row_per_rated_day_with_the_experiments_columns(self):
        people = [User.objects.create_user(f'ai-person-{n}') for n in range(5)]
        first = timezone.localdate() - timedelta(days=10)
        labels = ['LOW', 'MEDIUM', 'HIGH']
        for n, person in enumerate(people):
            for d in range(6):
                self.day_of(person, first + timedelta(days=d), 600 + 60 * d, 300, 100, label=labels[(n + d) % 3])
        # More of the first person's first day: camera samples and a finished task due that day.
        self.day_of(people[0], first, 0, 0, 0, present=[True, True, True, False], due_done=True, rate=False)
        DailySelfRating.objects.filter(employee=people[0], date=first).update(label='HIGH')
        lonely = User.objects.create_user('ai-no-activity')
        DailySelfRating.objects.create(employee=lonely, date=first, label='LOW')  # Rated, but nothing recorded.
        with TemporaryDirectory() as folder:
            out = Path(folder) / 'dataset.csv'
            output = StringIO()
            call_command('export_ai_dataset', out=out, stdout=output)
            rows = list(csv.DictReader(out.open(encoding='utf-8')))
        self.assertEqual(tuple(rows[0]), FIELDS)
        self.assertEqual(len(rows), 30)
        validate_rows(rows, 'real')  # ai/experiment.py accepts it as it is.
        self.assertIn('Ready for: python ai/experiment.py', output.getvalue())
        self.assertIn('1 rated days skipped', output.getvalue())
        names = {person.username for person in people} | {str(person.pk) for person in people}
        self.assertFalse(any(row['participant_id'] in names for row in rows))
        richest = next(row for row in rows if row['sample_id'].endswith(first.isoformat()) and row['label'] == 'High')
        self.assertEqual(float(richest['presence_ratio']), 0.75)
        self.assertEqual(float(richest['task_completion_ratio']), 1.0)

    def test_too_little_data_says_what_is_missing(self):
        person = User.objects.create_user('ai-single')
        self.day_of(person, timezone.localdate(), 600, 300, 100, label='LOW')
        with TemporaryDirectory() as folder:
            output = StringIO()
            call_command('export_ai_dataset', out=Path(folder) / 'x.csv', stdout=output)
        self.assertIn('29 more rows, 4 more people, every label', output.getvalue())
