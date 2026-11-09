from datetime import date, datetime, time, timedelta
from collections import defaultdict

from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.shortcuts import get_object_or_404

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ProductivityScore
from .serializers import ProductivityScoreSerializer
from .services import calculate_daily_score, ScoreNotReady

from activity.models import ComputerActivity, WebsiteActivity
from activity.reporting import camera_totals_for_day


User = get_user_model()


class ProductivityScoreViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductivityScoreSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = ProductivityScore.objects.select_related(
            "employee", "employee__department"
        )
        if user.is_admin_role:
            return queryset
        if user.is_manager and user.department_id:
            return queryset.filter(employee__department_id=user.department_id)
        return queryset.filter(employee=user)

    def _can_calculate_for(self, employee):
        requester = self.request.user
        if requester.is_admin_role:
            return
        if (
            requester.is_manager
            and requester.department_id
            and requester.department_id == employee.department_id
        ):
            return
        if requester.pk == employee.pk:
            return
        raise PermissionDenied(
            "You cannot calculate a score for this employee."
        )

    @action(detail=False, methods=["post"])
    def calculate(self, request):
        employee_id = request.data.get("employee_id", request.user.pk)
        employee = get_object_or_404(User, pk=employee_id)
        self._can_calculate_for(employee)

        try:
            score_date = date.fromisoformat(
                request.data.get(
                    "date", timezone.localdate().isoformat()
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {"date": "Use ISO format: YYYY-MM-DD."}
            ) from exc

        if score_date > timezone.localdate():
            raise ValidationError(
                {"date": "Future dates cannot be calculated."}
            )

        try:
            score = calculate_daily_score(employee, score_date)
        except ScoreNotReady as exc:
            raise ValidationError({
                "detail": str(exc),
                "task_ids": exc.task_ids,
            }) from exc

        return Response(
            self.get_serializer(score).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"])
    def dashboard(self, request):
        """Return dashboard-ready totals for one allowed employee and day."""
        employee_id = request.query_params.get(
            "employee_id", request.user.pk
        )
        employee = get_object_or_404(User, pk=employee_id)
        self._can_calculate_for(employee)

        try:
            report_date = date.fromisoformat(
                request.query_params.get(
                    "date", timezone.localdate().isoformat()
                )
            )
        except ValueError as exc:
            raise ValidationError(
                {"date": "Use ISO format: YYYY-MM-DD."}
            ) from exc

        camera_rows = [
            {"state": state, "seconds": seconds}
            for state, seconds in sorted(
                camera_totals_for_day(employee, report_date).items()
            )
        ]

        app_rows = (
            ComputerActivity.objects.filter(
                employee=employee,
                started_at__date=report_date,
            )
            .values("application", "category")
            .annotate(seconds=Sum("duration_seconds"))
            .order_by("-seconds", "application")
        )

        category_rows = (
            ComputerActivity.objects.filter(
                employee=employee,
                started_at__date=report_date,
            )
            .values("category")
            .annotate(seconds=Sum("duration_seconds"))
            .order_by("category")
        )

        website_rows = (
            WebsiteActivity.objects.filter(
                employee=employee,
                started_at__date=report_date,
            )
            .values("domain")
            .annotate(seconds=Sum("duration_seconds"))
            .order_by("-seconds", "domain")
        )

        score = ProductivityScore.objects.filter(
            employee=employee,
            date=report_date,
        ).first()

        return Response({
            "employee": {
                "id": employee.pk,
                "username": employee.username,
            },
            "date": report_date.isoformat(),
            "score": self.get_serializer(score).data if score else None,
            "camera": list(camera_rows),
            "applications": list(app_rows),
            "application_categories": list(category_rows),
            "websites": list(website_rows),
        })

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Aggregate a bounded date range for one employee or a department."""
        try:
            start = date.fromisoformat(request.query_params.get("start_date", timezone.localdate().isoformat()))
            end = date.fromisoformat(request.query_params.get("end_date", start.isoformat()))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"date": "Use ISO dates: YYYY-MM-DD."}) from exc
        if end < start or (end - start).days > 30:
            raise ValidationError({"date": "Choose a range from 1 to 31 days."})
        if end > timezone.localdate():
            raise ValidationError({"end_date": "Future dates cannot be reported."})

        department_id = request.query_params.get("department_id")
        employee_id = request.query_params.get("employee_id")
        if department_id and employee_id:
            raise ValidationError("Choose an employee or a department, not both.")
        if department_id:
            requester = request.user
            if department_id == "all" and requester.is_admin_role:
                employees = User.objects.filter(is_active=True).order_by("username")
            elif not requester.is_admin_role and not (
                requester.is_manager and str(requester.department_id) == str(department_id)
            ):
                raise PermissionDenied("You cannot view this department.")
            else:
                employees = User.objects.filter(department_id=department_id, is_active=True).order_by("username")
        else:
            employee = get_object_or_404(User, pk=employee_id or request.user.pk)
            self._can_calculate_for(employee)
            employees = User.objects.filter(pk=employee.pk)

        employee_ids = list(employees.values_list("pk", flat=True))
        if not employee_ids:
            return Response({"start_date": start.isoformat(), "end_date": end.isoformat(),
                             "employees": [], "applications": [], "application_categories": [],
                             "websites": [], "camera": [], "score": None})

        local_start = timezone.make_aware(datetime.combine(start, time.min))
        local_end = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min))
        query_start = local_start - timedelta(hours=1)
        app_rows = list(ComputerActivity.objects.filter(
            employee_id__in=employee_ids, started_at__gte=query_start, started_at__lt=local_end,
        ).values("employee_id", "application", "category", "started_at", "duration_seconds"))
        app_totals = defaultdict(float)
        category_totals = defaultdict(float)
        for row in app_rows:
            segment_end = row["started_at"] + timedelta(seconds=row["duration_seconds"])
            seconds = max(0, (min(local_end, segment_end) - max(local_start, row["started_at"])).total_seconds())
            if seconds:
                app_totals[(row["application"], row["category"])] += seconds
                category_totals[row["category"]] += seconds

        website_rows = list(WebsiteActivity.objects.filter(
            employee_id__in=employee_ids, started_at__gte=query_start, started_at__lt=local_end,
        ).values("domain", "started_at", "duration_seconds"))
        websites = defaultdict(float)
        for row in website_rows:
            segment_end = row["started_at"] + timedelta(seconds=row["duration_seconds"])
            seconds = max(0, (min(local_end, segment_end) - max(local_start, row["started_at"])).total_seconds())
            if seconds:
                websites[row["domain"]] += seconds

        camera = defaultdict(float)
        for timestamp, duration, state in ActivityEvent.objects.filter(
            employee_id__in=employee_ids, timestamp__gt=query_start,
            timestamp__lt=local_end,
        ).values_list("timestamp", "duration_seconds", "state").iterator():
            seconds = (min(local_end, timestamp) - max(local_start, timestamp - timedelta(seconds=duration))).total_seconds()
            if seconds > 0:
                camera[state] += seconds

        score_rows = ProductivityScore.objects.filter(employee_id__in=employee_ids, date__range=(start, end))
        score_values = list(score_rows.values_list("score", flat=True))
        average = (sum(float(value) for value in score_values) / len(score_values)) if score_values else None
        score = None if average is None else {
            "score": round(average, 2),
            "category": "HIGH" if average >= 80 else "MEDIUM" if average >= 60 else "LOW",
            "sample_days": len(score_values),
        }
        employee_rows = list(employees.values("id", "username", "first_name", "last_name", "department__name"))
        return Response({
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "employees": employee_rows,
            "applications": [{"application": name, "category": category, "seconds": seconds}
                             for (name, category), seconds in sorted(app_totals.items(), key=lambda item: -item[1])],
            "application_categories": [{"category": category, "seconds": seconds}
                                        for category, seconds in sorted(category_totals.items())],
            "websites": [{"domain": domain, "seconds": seconds}
                         for domain, seconds in sorted(websites.items(), key=lambda item: -item[1])],
            "camera": [{"state": state, "seconds": seconds} for state, seconds in sorted(camera.items())],
            "score": score,
        })
