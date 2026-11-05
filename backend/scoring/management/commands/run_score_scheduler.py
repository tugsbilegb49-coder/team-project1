"""Small process scheduler for daily score refreshes in Docker or a VM."""

from datetime import timedelta
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Run calculate_daily_scores once per day at a local server time."

    def add_arguments(self, parser):
        parser.add_argument("--hour", type=int, default=23, choices=range(24))
        parser.add_argument("--minute", type=int, default=55, choices=range(60))

    def handle(self, *args, **options):
        hour, minute = options["hour"], options["minute"]
        self.stdout.write(f"Score scheduler running daily at {hour:02d}:{minute:02d}.")
        while True:
            now = timezone.localtime()
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            time.sleep((next_run - now).total_seconds())
            target_date = timezone.localdate().isoformat()
            call_command("calculate_daily_scores", date=target_date)
