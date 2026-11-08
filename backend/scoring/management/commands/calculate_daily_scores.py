from datetime import date

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.management.base import BaseCommand, CommandError

from scoring.models import ProductivityScore
from scoring.services import calculate_daily_score, has_work_on, ScoreNotReady


class Command(BaseCommand):
    help = 'Calculate or refresh daily productivity scores for active employees.'

    def add_arguments(self, parser):
        parser.add_argument('--date', default=timezone.localdate().isoformat(), help='ISO date (YYYY-MM-DD)')
        parser.add_argument('--employee', help='Optional username to calculate for one employee')

    def handle(self, *args, **options):
        try:
            score_date = date.fromisoformat(options['date'])
        except ValueError as exc:
            raise CommandError('Use --date YYYY-MM-DD') from exc

        user_model = get_user_model()
        users = user_model.objects.filter(is_active=True)
        if options.get('employee'):
            users = users.filter(username=options['employee'])
            if not users.exists():
                raise CommandError('Employee username was not found.')

        count = 0
        skipped = 0
        idle = 0
        for employee in users.iterator():
            if not has_work_on(employee, score_date):
                # Nothing was due or recorded: no score, and no stale 0 from an earlier run.
                ProductivityScore.objects.filter(employee=employee, date=score_date).delete()
                idle += 1
                continue
            try:
                result = calculate_daily_score(employee, score_date)
            except ScoreNotReady as exc:
                skipped += 1
                self.stderr.write(f'Skipped {employee.username}: {exc} Task IDs: {exc.task_ids}')
                continue
            count += 1
            self.stdout.write(f'{employee.username}: {result.score} ({result.category})')
        self.stdout.write(
            self.style.SUCCESS(
                f'Calculated {count} score(s) for {score_date}; skipped {skipped}; {idle} with nothing to score.'
            )
        )
