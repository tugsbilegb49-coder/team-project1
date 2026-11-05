"""Import the webcam monitor's CSV output for one employee."""

import csv
from datetime import datetime
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from activity.models import ActivityEvent


class Command(BaseCommand):
    help = "Import data/activity_log.csv for an employee. Existing identical rows are skipped."

    def add_arguments(self, parser):
        parser.add_argument("csv_file", help="Path to activity_log.csv")
        parser.add_argument("--employee", required=True, help="Username of the employee who owns this log")

    def handle(self, *args, **options):
        path = Path(options["csv_file"])
        if not path.is_file():
            raise CommandError(f"CSV file not found: {path}")

        user_model = get_user_model()
        try:
            employee = user_model.objects.get(username=options["employee"])
        except user_model.DoesNotExist as exc:
            raise CommandError(f"No user named '{options['employee']}'.") from exc

        created = skipped = 0
        valid_states = set(ActivityEvent.State.values)
        with path.open(newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            required = {"timestamp", "state", "duration_seconds"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise CommandError("CSV must contain timestamp, state, and duration_seconds columns.")

            for line_number, row in enumerate(reader, start=2):
                state = (row.get("state") or "").strip()
                if state not in valid_states:
                    raise CommandError(f"Line {line_number}: unsupported state '{state}'.")
                try:
                    timestamp = datetime.fromisoformat(row["timestamp"])
                    if timezone.is_naive(timestamp):
                        timestamp = timezone.make_aware(timestamp, timezone.get_current_timezone())
                    duration = float(row["duration_seconds"])
                    if duration < 0:
                        raise ValueError("duration must be non-negative")
                except (TypeError, ValueError) as exc:
                    raise CommandError(f"Line {line_number}: invalid timestamp or duration.") from exc

                event, was_created = ActivityEvent.objects.get_or_create(
                    employee=employee,
                    timestamp=timestamp,
                    state=state,
                    duration_seconds=duration,
                    source_person_id=(row.get("person_id") or "").strip(),
                )
                if was_created:
                    created += 1
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(f"Imported {created} events; skipped {skipped} duplicates."))

