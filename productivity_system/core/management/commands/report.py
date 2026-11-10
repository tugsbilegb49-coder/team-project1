from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Avg, Count, Sum

from core.date_ranges import local_datetime_bounds
from core.models import CameraAnalytics, ComputerActivity


class Command(BaseCommand):
    help = "Aggregate query tailan (employee bureer)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--from",
            dest="start_date",
            type=date.fromisoformat,
            help="Include records from this date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--to",
            dest="end_date",
            type=date.fromisoformat,
            help="Include records through this date (YYYY-MM-DD).",
        )

    @staticmethod
    def _value(value):
        return value if value is not None else 0

    def handle(self, *args, **options):
        start_date = options["start_date"]
        end_date = options["end_date"]
        if start_date and end_date and start_date > end_date:
            raise CommandError("--from date must be before or equal to --to date.")
        start_at, end_at = local_datetime_bounds(start_date, end_date)

        self.stdout.write("== Computer activity ==")
        activities = ComputerActivity.objects.all()
        cameras = CameraAnalytics.objects.all()
        if start_date:
            activities = activities.filter(date__gte=start_date)
            cameras = cameras.filter(observed_at__gte=start_at)
        if end_date:
            activities = activities.filter(date__lte=end_date)
            cameras = cameras.filter(observed_at__lt=end_at)
        if start_date or end_date:
            self.stdout.write(
                f"Period: {start_date or 'beginning'} to {end_date or 'present'}"
            )

        rows = (
            activities.values("employee__full_name")
            .annotate(
                active=Sum("active_seconds"),
                idle=Sum("idle_seconds"),
                keys=Sum("key_count"),
                clicks=Sum("click_count"),
            )
            .order_by("employee__full_name")
        )
        if not rows.exists():
            self.stdout.write("No computer activity records found.")
        for r in rows:
            self.stdout.write(
                f"{r['employee__full_name']:<20} active={self._value(r['active'])}s "
                f"idle={self._value(r['idle'])}s keys={self._value(r['keys'])} "
                f"clicks={self._value(r['clicks'])}"
            )

        self.stdout.write("== Camera ==")
        cams = (
            cameras.values("employee__full_name")
            .annotate(n=Count("id"), avg_conf=Avg("confidence"))
            .order_by("employee__full_name")
        )
        if not cams.exists():
            self.stdout.write("No camera records found.")
        for r in cams:
            self.stdout.write(
                f"{r['employee__full_name']:<20} records={r['n']} "
                f"avg_confidence={r['avg_conf']:.2f}"
            )
