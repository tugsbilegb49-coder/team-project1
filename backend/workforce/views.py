from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from users.models import Department
from users.permissions import IsAdminOrManager, IsSystemAdmin
from .models import Task
from .serializers import DepartmentSerializer, TaskSerializer


class DepartmentViewSet(viewsets.ModelViewSet):
    serializer_class = DepartmentSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Department.objects.all()
        if user.is_admin_role:
            return queryset
        if user.department_id:
            return queryset.filter(pk=user.department_id)
        return queryset.none()

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsSystemAdmin()]
        return [IsAuthenticated()]


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Task.objects.select_related("employee", "assigned_by", "employee__department")
        if user.is_admin_role:
            return queryset
        if user.is_manager and user.department_id:
            return queryset.filter(employee__department_id=user.department_id)
        return queryset.filter(employee=user)

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def _ensure_employee_in_manager_department(self, employee):
        user = self.request.user
        if user.is_manager and employee.department_id != user.department_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Managers can only manage employees in their own department.")

    def perform_create(self, serializer):
        employee = serializer.validated_data["employee"]
        self._ensure_employee_in_manager_department(employee)
        completed_at = timezone.now() if serializer.validated_data.get("status") == Task.Status.DONE else None
        serializer.save(assigned_by=self.request.user, completed_at=completed_at)

    def perform_update(self, serializer):
        employee = serializer.validated_data.get("employee", serializer.instance.employee)
        self._ensure_employee_in_manager_department(employee)
        task = serializer.save()
        if task.status == Task.Status.DONE and task.completed_at is None:
            task.completed_at = timezone.now()
            task.save(update_fields=["completed_at", "updated_at"])

