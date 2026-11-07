from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from users.models import User
from users.operations import StrictSerializer, audit_event
from .models import Task, TaskTransfer, TaskWorkSession
from . import workflow


class EmptyInput(StrictSerializer):
    pass


class ProgressInput(StrictSerializer):
    percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)
    expected_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)


class TransferInput(StrictSerializer):
    recipient = serializers.IntegerField(min_value=1)
    note = serializers.CharField(max_length=1000, allow_blank=True, required=False, default='')


class TransferDecision(StrictSerializer):
    request_id = serializers.IntegerField(min_value=1)
    decision = serializers.ChoiceField(choices=['accept', 'decline', 'cancel'])


class SessionInput(StrictSerializer):
    session_id = serializers.IntegerField(min_value=1)


def validated(serializer_type, request):
    serializer = serializer_type(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class TaskActions:
    def locked_task(self):
        # Lock only the task row: nullable joins and DISTINCT cannot be FOR UPDATE on PostgreSQL.
        visible = self.get_object()
        task = Task.objects.select_for_update().get(pk=visible.pk)
        if not workflow.visible_tasks(self.request.user).filter(pk=task.pk).exists():
            raise PermissionDenied('Даалгаварт хандах эрх өөрчлөгдсөн.')
        return task

    def task_response(self, task):
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=['get'], url_path='transfer-recipients')
    def transfer_recipients(self, request, pk=None):
        rows = workflow.recipients(request.user, self.get_object())
        return Response([{'id': user.pk, 'username': user.username, 'name': user.get_full_name() or user.username} for user in rows])

    @action(detail=True, methods=['post'], url_path='transfer-request')
    @transaction.atomic
    def transfer_request(self, request, pk=None):
        data = validated(TransferInput, request)
        task = self.locked_task()
        recipient = workflow.recipients(request.user, task).filter(pk=data['recipient']).first()
        if not recipient:
            raise ValidationError('Идэвхтэй, өөрийн хэлтсийн өөр гишүүн сонгоно уу. Админ бүх хэлтсээс сонгож болно.')
        if task.status == Task.Status.DONE or task.transfer_count >= 2:
            raise workflow.Conflict('Дууссан эсвэл хоёр удаа шилжсэн даалгаврыг шилжүүлэхгүй.')
        if task.transfers.filter(status='PENDING').exists():
            raise workflow.Conflict('Энэ даалгаварт хүлээгдэж буй хүсэлт байна.')
        transfer = TaskTransfer.objects.create(task=task, from_employee=task.employee, to_employee=recipient,
            requested_by=request.user, from_name=task.employee.username, to_name=recipient.username, note=data['note'])
        audit_event(request.user, 'task', task.pk, 'transfer_request', {'recipient': recipient.username, 'request_id': transfer.pk}, task.employee)
        return self.task_response(task)

    @action(detail=True, methods=['post'], url_path='transfer-respond')
    @transaction.atomic
    def transfer_respond(self, request, pk=None):
        data = validated(TransferDecision, request)
        task = self.locked_task()
        transfer = task.transfers.filter(pk=data['request_id']).first()
        if not transfer:
            raise ValidationError('Энэ даалгаврын хүсэлт олдсонгүй.')
        decision = data['decision']
        if decision in ('accept', 'decline') and transfer.to_employee_id != request.user.pk:
            raise PermissionDenied('Зөвхөн хүлээн авагч зөвшөөрөх эсвэл татгалзана.')
        if decision == 'cancel' and not (request.user.pk in (transfer.requested_by_id, task.employee_id) or workflow.can_manage(request.user, task)):
            raise PermissionDenied('Хүсэлт цуцлах эрхгүй.')
        if transfer.status != 'PENDING':
            raise workflow.Conflict('Энэ хүсэлтийг аль хэдийн шийдвэрлэсэн.')
        now = timezone.now()
        if decision == 'accept':
            if task.status == Task.Status.DONE or task.transfer_count >= 2 or task.employee_id != transfer.from_employee_id:
                raise workflow.Conflict('Даалгаврын төлөв өөрчлөгдсөн. Шинэ хүсэлт шаардлагатай.')
            sender = transfer.requested_by
            if not sender or (not sender.is_admin_role and (not task.employee.department_id or task.employee.department_id != request.user.department_id)):
                raise workflow.Conflict('Хэлтсийн тохиргоо өөрчлөгдсөн. Шинэ хүсэлт шаардлагатай.')
            workflow.contribution(task, task.employee)
            workflow.stop_task(task, now)
            task.employee = request.user
            task.transfer_count += 1
            task.save(update_fields=['employee', 'transfer_count', 'updated_at'])
            workflow.contribution(task, request.user)
        transfer.status = {'accept': 'ACCEPTED', 'decline': 'DECLINED', 'cancel': 'CANCELLED'}[decision]
        transfer.responded_at = now
        transfer.save(update_fields=['status', 'responded_at'])
        audit_event(request.user, 'task', task.pk, 'transfer_'+decision,
                    {'from': transfer.from_name, 'to': transfer.to_name, 'request_id': transfer.pk}, task.employee)
        return self.task_response(task)

    @action(detail=True, methods=['post'], url_path='progress')
    @transaction.atomic
    def progress(self, request, pk=None):
        data = validated(ProgressInput, request)
        task = self.locked_task()
        workflow.require_owner(request.user, task)
        row = workflow.contribution(task, request.user)
        if row.percent != data['expected_percent']:
            raise workflow.Conflict('Хувь өөр цонхноос шинэчлэгдсэн. Жагсаалтаа шинэчилнэ үү.')
        other = task.contributions.exclude(pk=row.pk).aggregate(total=Sum('percent'))['total'] or Decimal(0)
        if other + data['percent'] > 100:
            raise ValidationError({'percent': f'Бусад гишүүдийн хувийг оруулаад 100%-аас хэтрэхгүй. Таны дээд хэмжээ {100-other}%.'})
        previous = row.percent
        row.percent = data['percent']
        row.save(update_fields=['percent'])
        audit_event(request.user, 'task', task.pk, 'progress', {'percent': {'before': str(previous), 'after': str(row.percent)}}, request.user)
        return self.task_response(task)

    @action(detail=True, methods=['post'], url_path='work-start')
    @transaction.atomic
    def work_start(self, request, pk=None):
        validated(EmptyInput, request)
        task = self.locked_task()
        workflow.require_owner(request.user, task)
        if task.status == Task.Status.DONE:
            raise workflow.Conflict('Дууссан даалгаварт цаг бүртгэхгүй.')
        User.objects.select_for_update().get(pk=request.user.pk)
        now = timezone.now()
        running = TaskWorkSession.objects.filter(employee=request.user, ended_at__isnull=True).first()
        if running:
            if running.last_heartbeat + timedelta(seconds=workflow.LEASE_SECONDS) <= now:
                workflow.finish(running, now)
            elif running.contribution.task_id == task.pk:
                return Response(workflow.work_state(request.user, now))
            else:
                raise workflow.Conflict('Өөр даалгаврын цаг ажиллаж байна. Эхлээд түүнийг зогсооно уу.')
        row = workflow.contribution(task, request.user)
        TaskWorkSession.objects.create(contribution=row, employee=request.user, started_at=now, last_heartbeat=now)
        if task.status == Task.Status.TODO:
            task.status = Task.Status.IN_PROGRESS
            task.save(update_fields=['status', 'updated_at'])
        audit_event(request.user, 'task', task.pk, 'work_start', {}, request.user)
        return Response(workflow.work_state(request.user, now), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='work-stop')
    @transaction.atomic
    def work_stop(self, request, pk=None):
        data = validated(SessionInput, request)
        task = self.locked_task()
        User.objects.select_for_update().get(pk=request.user.pk)
        session = TaskWorkSession.objects.filter(pk=data['session_id'], employee=request.user, contribution__task=task).first()
        if not session:
            raise PermissionDenied('Зөвхөн өөрийн цагийг зогсооно.')
        if session.ended_at is None:
            workflow.finish(session)
            audit_event(request.user, 'task', task.pk, 'work_stop', {}, request.user)
        return Response(workflow.work_state(request.user))

    @action(detail=False, methods=['get', 'post'], url_path='work-session')
    @transaction.atomic
    def work_session(self, request):
        if request.method == 'POST':
            data = validated(SessionInput, request)
            session = TaskWorkSession.objects.filter(pk=data['session_id'], employee=request.user).first()
            if not session:
                raise PermissionDenied('Өөрийн цагийн session шаардлагатай.')
            task = Task.objects.select_for_update().get(pk=session.contribution.task_id)
            User.objects.select_for_update().get(pk=request.user.pk)
            session.refresh_from_db()
            now = timezone.now()
            if session.ended_at is None:
                if session.last_heartbeat + timedelta(seconds=workflow.LEASE_SECONDS) <= now or task.employee_id != request.user.pk or task.status == Task.Status.DONE:
                    workflow.finish(session, now)
                else:
                    session.last_heartbeat = now
                    session.save(update_fields=['last_heartbeat'])
        return Response(workflow.work_state(request.user))
