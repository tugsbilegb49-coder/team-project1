from datetime import date

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
from .services import calculate_daily_score
from activity.models import ActivityEvent, ComputerActivity


User = get_user_model()


class ProductivityScoreViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductivityScoreSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = ProductivityScore.objects.select_related("employee", "employee__department")
        if user.is_admin_role:
            return queryset
        if user.is_manager and user.department_id:
            return queryset.filter(employee__department_id=user.department_id)
        return queryset.filter(employee=user)

    def _can_calculate_for(self, employee):
        requester = self.request.user
        if requester.is_admin_role:
            return
        if requester.is_manager and requester.department_id == employee.department_id:
            return
        if requester.pk == employee.pk:
            return
        raise PermissionDenied("You cannot calculate a score for this employee.")

    @action(detail=False, methods=["post"])
    def calculate(self, request):
        employee_id = request.data.get("employee_id", request.user.pk)
        employee = get_object_or_404(User, pk=employee_id)
        self._can_calculate_for(employee)
        try:
            score_date = date.fromisoformat(request.data.get("date", date.today().isoformat()))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"date": "Use ISO format: YYYY-MM-DD."}) from exc

        score = calculate_daily_score(employee, score_date)
        return Response(self.get_serializer(score).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def dashboard(self, request):
        """Return dashboard-ready totals for one allowed employee and day."""
        employee_id = request.query_params.get("employee_id", request.user.pk)
        employee = get_object_or_404(User, pk=employee_id)
        self._can_calculate_for(employee)
        try:
            report_date = date.fromisoformat(request.query_params.get("date", date.today().isoformat()))
        except ValueError as exc:
            raise ValidationError({"date": "Use ISO format: YYYY-MM-DD."}) from exc

        camera_rows = (
            ActivityEvent.objects.filter(employee=employee, timestamp__date=report_date)
            .values("state")
            .annotate(seconds=Sum("duration_seconds"))
            .order_by("state")
        )
        app_rows = (
            ComputerActivity.objects.filter(employee=employee, started_at__date=report_date)
            .values("application", "category")
            .annotate(seconds=Sum("duration_seconds"))
            .order_by("-seconds", "application")
        )
        category_rows = (
            ComputerActivity.objects.filter(employee=employee, started_at__date=report_date)
            .values("category")
            .annotate(seconds=Sum("duration_seconds"))
            .order_by("category")
        )
        score = ProductivityScore.objects.filter(employee=employee, date=report_date).first()
        return Response({
            "employee": {"id": employee.pk, "username": employee.username},
            "date": report_date.isoformat(),
            "score": self.get_serializer(score).data if score else None,
            "camera": list(camera_rows),
            "applications": list(app_rows),
            "application_categories": list(category_rows),
        })

