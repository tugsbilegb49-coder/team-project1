"""Assignment handoffs and explicit task time; unrelated app usage is never attributed to a task."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied

from users.models import User
from .models import Task, TaskContribution, TaskTransfer, TaskWorkSession

LEASE_SECONDS = 90


class Conflict(APIException):
    status_code = 409
    default_detail = 'Даалгаврын төлөв өөрчлөгдсөн. Шинэчлээд дахин оролдоно уу.'


def visible_tasks(user):
    rows = Task.objects.all()
    if user.is_admin_role:
        return rows
    own = Q(employee=user) | Q(contributions__employee=user) | Q(transfers__from_employee=user)
    own |= Q(transfers__to_employee=user, transfers__status=TaskTransfer.Status.PENDING)
    if user.is_manager and user.department_id:
        own |= Q(employee__department_id=user.department_id)
    return rows.filter(own).distinct()


def can_manage(user, task):
    return user.is_admin_role or (user.is_manager and user.department_id and task.employee.department_id == user.department_id)


def require_owner(user, task):
    if task.employee_id != user.pk:
        raise PermissionDenied('Зөвхөн одоогийн хариуцагч өөрийн цаг, хувийг бүртгэнэ.')


def recipients(user, task):
    if not (task.employee_id == user.pk or can_manage(user, task)):
        raise PermissionDenied('Энэ даалгаврыг шилжүүлэх эрхгүй.')
    rows = User.objects.filter(is_active=True).exclude(pk=task.employee_id)
    if not user.is_admin_role:
        if not user.department_id:
            return rows.none()
        rows = rows.filter(department_id=user.department_id)
    return rows.order_by('username')


def contribution(task, user):
    return TaskContribution.objects.get_or_create(task=task, employee=user, defaults={'employee_name': user.username})[0]


def session_end(session, now=None):
    return session.ended_at or min(now or timezone.now(), session.last_heartbeat + timedelta(seconds=LEASE_SECONDS))


def seconds(session, now=None):
    return max(0, (session_end(session, now) - session.started_at).total_seconds())


def finish(session, now=None):
    if session.ended_at is None:
        session.ended_at = max(session.started_at, session_end(session, now))
        session.save(update_fields=['ended_at'])


def stop_task(task, now=None):
    now = now or timezone.now()
    for session in TaskWorkSession.objects.filter(contribution__task=task, ended_at__isnull=True):
        finish(session, now)


def close_task(task):
    stop_task(task)
    task.transfers.filter(status=TaskTransfer.Status.PENDING).update(status=TaskTransfer.Status.CANCELLED, responded_at=timezone.now())


def work_state(user, now=None):
    now = now or timezone.now()
    session = TaskWorkSession.objects.select_related('contribution__task').filter(employee=user, ended_at__isnull=True).first()
    if not session:
        return {'session': None, 'server_now': now}
    task = session.contribution.task
    deadline = session.last_heartbeat + timedelta(seconds=LEASE_SECONDS)
    running = deadline > now and task.employee_id == user.pk and task.status != Task.Status.DONE
    return {'server_now': now, 'session': {
        'id': session.pk, 'task_id': task.pk, 'title': task.title,
        'started_at': session.started_at, 'lease_expires_at': deadline,
        'seconds': int(seconds(session, now)), 'running': running,
    }}


def collaboration_data(task):
    now = timezone.now()
    people = []
    for row in task.contributions.all():
        sessions = list(row.sessions.all())
        people.append({'employee': row.employee_id, 'username': row.employee_name,
                       'percent': str(row.percent), 'seconds': int(sum(seconds(item, now) for item in sessions)),
                       'running': any(item.ended_at is None and item.last_heartbeat + timedelta(seconds=LEASE_SECONDS) > now for item in sessions)})
    total_seconds = sum(row['seconds'] for row in people)
    for row in people:
        row['time_share_percent'] = round(row['seconds'] * 100 / total_seconds, 1) if total_seconds else 0
    transfers = [{'id': row.pk, 'from_employee': row.from_employee_id, 'to_employee': row.to_employee_id,
                  'requested_by': row.requested_by_id, 'from_name': row.from_name, 'to_name': row.to_name,
                  'note': row.note, 'status': row.status, 'created_at': row.created_at, 'responded_at': row.responded_at}
                 for row in task.transfers.all()]
    return {'contributions': people, 'total_seconds': total_seconds,
            'progress_percent': str(sum((Decimal(row['percent']) for row in people), Decimal(0))),
            'pending_transfer': next((row for row in transfers if row['status'] == 'PENDING'), None), 'transfers': transfers}
