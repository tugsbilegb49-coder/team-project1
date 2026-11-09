from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import Department
from users.permissions import IsAdminOrManager, IsSystemAdmin
from users.operations import audit_event, audit_update, snapshot
from .models import Task
from .serializers import DepartmentSerializer, TaskSerializer
from .task_actions import TaskActions
from . import workflow


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
        if self.action in {'create', 'update', 'partial_update', 'destroy'}:
            return [IsSystemAdmin()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        with transaction.atomic():
            department = serializer.save()
            audit_event(
                self.request.user,
                'department',
                department.pk,
                'create',
                {'name': department.name, 'description': department.description},
            )

    def perform_update(self, serializer):
        department = serializer.instance
        fields = ("name", "description")
        before = snapshot(department, fields)
        with transaction.atomic():
            department = serializer.save()
            audit_update(self.request.user, 'department', department, before, fields)

    def perform_destroy(self, instance):
        with transaction.atomic():
            audit_event(
                self.request.user,
                'department',
                instance.pk,
                'delete',
                {'name': instance.name, 'description': instance.description},
            )
            instance.delete()


class TaskViewSet(TaskActions, viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            workflow.visible_tasks(self.request.user)
            .select_related('employee', 'assigned_by', 'employee__department')
            .prefetch_related('contributions__sessions', 'transfers')
        )

    def get_permissions(self):
        if self.action in {'create', 'update', 'partial_update', 'destroy'}:
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def _ensure_employee_in_manager_department(self, employee):
        user = self.request.user
        if (
            not user.is_admin_role
            and user.is_manager
            and (not user.department_id or employee.department_id != user.department_id)
        ):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied('Managers can only manage employees in their own department.')

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        task = self.locked_task()
        self._ensure_employee_in_manager_department(task.employee)
        serializer = self.get_serializer(task, data=request.data, partial=kwargs.pop('partial', False))
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        task = self.locked_task()
        self._ensure_employee_in_manager_department(task.employee)
        self.perform_destroy(task)
        return Response(status=204)

    @transaction.atomic
    def perform_create(self, serializer):
        employee = serializer.validated_data['employee']
        self._ensure_employee_in_manager_department(employee)
        completed_at = timezone.now() if serializer.validated_data.get('status') == Task.Status.DONE else None
        task = serializer.save(assigned_by=self.request.user, completed_at=completed_at)
        from users.operations import audit_update

        audit_update(
            self.request.user,
            'task',
            task,
            {},
            ('employee_id', 'title', 'status', 'due_date', 'quality_score'),
            task.employee,
            action='create',
        )

    @transaction.atomic
    def perform_update(self, serializer):
        from users.operations import audit_update, snapshot

        fields = ('employee_id', 'title', 'status', 'due_date', 'quality_score', 'completed_at')
        before = snapshot(serializer.instance, fields)
        employee = serializer.validated_data.get('employee', serializer.instance.employee)
        self._ensure_employee_in_manager_department(employee)
        task = serializer.save()
        if task.status != Task.Status.DONE and task.completed_at is not None:
            task.completed_at = None
            task.save(update_fields=['completed_at', 'updated_at'])
        if task.status == Task.Status.DONE and task.completed_at is None:
            task.completed_at = timezone.now()
            task.save(update_fields=['completed_at', 'updated_at'])
        if task.status == Task.Status.DONE:
            workflow.close_task(task)
        audit_update(self.request.user, 'task', task, before, fields, task.employee)

    @transaction.atomic
    def perform_destroy(self, instance):
        from users.operations import audit_event

        audit_event(self.request.user, 'task', instance.pk, 'delete', {}, instance.employee)
        instance.delete()
