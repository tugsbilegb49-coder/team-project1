"""Refresh recent daily scores while the local launcher or Docker is running."""

import argparse
from datetime import timedelta
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, close_old_connections
from django.utils import timezone


def interval_seconds(value):
    try:
        seconds = int(value)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError('Interval must be an integer.') from exc
    if not 10 <= seconds <= 3600:
        raise argparse.ArgumentTypeError('Interval must be between 10 and 3600 seconds.')
    return seconds


class Command(BaseCommand):
    help = 'Refresh today and yesterday at startup and every 60 seconds (Asia/Ulaanbaatar).'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=interval_seconds, default=60, help='Refresh interval, 10–3600 seconds.')
        parser.add_argument('--once', action='store_true', help='Refresh both days once and exit.')

    def refresh(self):
        today = timezone.localdate()
        failures = []
        for day in (today - timedelta(days=1), today):
            close_old_connections()
            try:
                call_command('calculate_daily_scores', date=day.isoformat(), stdout=self.stdout, stderr=self.stderr)
            except (DatabaseError, CommandError) as exc:
                failures.append(day)
                self.stderr.write(f'Refresh failed for {day}: {exc}. Will retry next cycle.')
            finally:
                close_old_connections()
        return failures

    def handle(self, *args, **options):
        self.stdout.write(
            f'Score scheduler: today + yesterday, interval {options["interval"]}s, timezone {timezone.get_current_timezone_name()}.'
        )
        try:
            while True:
                failures = self.refresh()
                if options['once']:
                    if failures:
                        raise CommandError('Some score dates could not be refreshed.')
                    return
                # Short waits allow prompt shutdown and avoid one day-long sleep.
                deadline = time.monotonic() + options['interval']
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(30, remaining))
        except KeyboardInterrupt:
            self.stdout.write('Score scheduler stopped.')
