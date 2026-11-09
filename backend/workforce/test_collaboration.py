from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import AuditEntry, Department, User
from .models import Task, TaskContribution, TaskTransfer, TaskWorkSession


class TaskCollaborationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        team = Department.objects.create(name='Work team')
        other = Department.objects.create(name='Other team')
        cls.a = User.objects.create_user('alice', department=team)
        cls.b = User.objects.create_user('bob', department=team)
        cls.c = User.objects.create_user('carol', department=team)
        cls.foreign = User.objects.create_user('foreign', department=other)
        cls.inactive = User.objects.create_user('inactive', department=team, is_active=False)
        cls.manager = User.objects.create_user('team-manager', department=team, role='MANAGER')
        cls.admin = User.objects.create_user('site-admin', role='ADMIN')

    def setUp(self):
        cache.clear()
        self.task = Task.objects.create(title='Shared work', employee=self.a)
        self.client = APIClient()
        self.client.force_authenticate(self.a)
        self.now = timezone.now()

    def post(self, action, data=None, user=None, task=None, at=None):
        self.client.force_authenticate(user or self.a)
        with patch('django.utils.timezone.now', return_value=at or self.now):
            return self.client.post(f'/api/tasks/{(task or self.task).pk}/{action}/', data or {}, format='json')

    def request_transfer(self, target, sender=None):
        response = self.post('transfer-request', {'recipient': target.pk, 'note': 'Handoff notes'}, user=sender)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['collaboration']['pending_transfer']['id']

    def accept(self, request_id, user, at=None):
        return self.post('transfer-respond', {'request_id': request_id, 'decision': 'accept'}, user=user, at=at)

    def test_handoff_requires_recipient_acceptance_and_retains_previous_contribution(self):
        started = self.post('work-start')
        self.assertEqual(started.status_code, 201)
        self.assertEqual(self.post('progress', {'percent': 35, 'expected_percent': 0}).status_code, 200)
        request_id = self.request_transfer(self.b)
        self.task.refresh_from_db()
        self.assertEqual(self.task.employee, self.a)
        self.assertEqual(self.task.transfer_count, 0)
        self.assertEqual(self.accept(request_id, self.admin).status_code, 403)
        self.assertEqual(self.accept(request_id, self.c).status_code, 404)
        accepted = self.accept(request_id, self.b, self.now + timedelta(seconds=30))
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(accepted.data['employee'], self.b.pk)
        self.assertEqual(accepted.data['transfer_count'], 1)
        self.assertEqual(accepted.data['collaboration']['contributions'][0]['seconds'], 30)
        self.assertEqual(Decimal(accepted.data['collaboration']['contributions'][0]['percent']), 35)
        self.assertIsNotNone(TaskWorkSession.objects.get().ended_at)
        self.assertEqual(self.post('work-start').status_code, 403)
        self.assertEqual(self.post('progress', {'percent': 40, 'expected_percent': 35}).status_code, 403)
        self.client.force_authenticate(self.a)
        self.assertEqual(self.client.get(f'/api/tasks/{self.task.pk}/').status_code, 200)
        self.assertEqual(self.post('work-start', user=self.b).status_code, 201)

    def test_only_two_accepted_handoffs_and_duplicate_response_cannot_increment(self):
        first = self.request_transfer(self.b)
        self.assertEqual(self.accept(first, self.b).status_code, 200)
        self.assertEqual(self.accept(first, self.b).status_code, 409)
        second = self.request_transfer(self.c, sender=self.b)
        self.assertEqual(self.accept(second, self.c).status_code, 200)
        self.assertEqual(self.post('transfer-request', {'recipient': self.a.pk}, user=self.c).status_code, 409)
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.patch(f'/api/tasks/{self.task.pk}/', {'employee': self.a.pk}, format='json').status_code, 400
        )
        self.task.refresh_from_db()
        self.assertEqual((self.task.employee_id, self.task.transfer_count), (self.c.pk, 2))
        self.assertEqual(TaskTransfer.objects.filter(status='ACCEPTED').count(), 2)

    def test_pending_duplicate_decline_and_cancel_rules(self):
        first = self.request_transfer(self.b)
        self.assertEqual(self.post('transfer-request', {'recipient': self.c.pk}).status_code, 409)
        self.assertEqual(self.post('transfer-respond', {'request_id': first, 'decision': 'decline'}).status_code, 403)
        self.assertEqual(
            self.post('transfer-respond', {'request_id': first, 'decision': 'decline'}, user=self.b).status_code, 200
        )
        second = self.request_transfer(self.c)
        self.assertEqual(
            self.post('transfer-respond', {'request_id': second, 'decision': 'cancel'}, user=self.b).status_code, 404
        )
        self.assertEqual(self.post('transfer-respond', {'request_id': second, 'decision': 'cancel'}).status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.transfer_count, 0)
        self.assertEqual(self.task.employee_id, self.a.pk)

    def test_recipient_directory_and_request_are_scoped_and_do_not_leak_email(self):
        response = self.client.get(f'/api/tasks/{self.task.pk}/transfer-recipients/')
        self.assertEqual({row['id'] for row in response.data}, {self.b.pk, self.c.pk, self.manager.pk})
        self.assertNotIn('email', str(response.data))
        for recipient in (self.foreign, self.inactive, self.a):
            self.assertEqual(self.post('transfer-request', {'recipient': recipient.pk}).status_code, 400)
        self.client.force_authenticate(self.foreign)
        self.assertEqual(self.client.get(f'/api/tasks/{self.task.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/tasks/{self.task.pk}/transfer-recipients/').status_code, 404)
        self.assertEqual(
            self.post('transfer-request', {'recipient': self.foreign.pk}, user=self.admin).status_code, 200
        )

    def test_percent_is_personal_total_bounded_and_stale_update_rejected(self):
        self.assertEqual(self.post('progress', {'percent': 35, 'expected_percent': 0}).status_code, 200)
        self.assertEqual(self.post('progress', {'percent': 45, 'expected_percent': 0}).status_code, 409)
        request_id = self.request_transfer(self.b)
        self.assertEqual(self.accept(request_id, self.b).status_code, 200)
        for value in (66, -1, 'NaN', 'Infinity', '0.001'):
            with self.subTest(value=value):
                self.assertEqual(
                    self.post('progress', {'percent': value, 'expected_percent': 0}, user=self.b).status_code, 400
                )
        response = self.post('progress', {'percent': 65, 'expected_percent': 0}, user=self.b)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data['collaboration']['progress_percent']), 100)
        self.assertEqual(TaskContribution.objects.get(employee=self.a).percent, 35)
        self.assertEqual(
            self.post('progress', {'percent': 10, 'expected_percent': 65}, user=self.admin).status_code, 403
        )

    def test_timer_is_one_task_per_user_idempotent_and_counts_server_time(self):
        other = Task.objects.create(title='Another task', employee=self.a)
        first = self.post('work-start')
        session_id = first.data['session']['id']
        second = self.post('work-start', at=self.now + timedelta(seconds=10))
        self.assertEqual(second.data['session']['id'], session_id)
        self.assertEqual(TaskWorkSession.objects.count(), 1)
        self.assertEqual(self.post('work-start', task=other).status_code, 409)
        self.assertEqual(self.post('work-stop', {'session_id': session_id}, user=self.admin).status_code, 403)
        self.assertEqual(
            self.post('work-stop', {'session_id': session_id}, at=self.now + timedelta(seconds=45)).status_code, 200
        )
        self.assertEqual((TaskWorkSession.objects.get().ended_at - self.now).total_seconds(), 45)
        self.assertEqual(self.post('work-start', task=other, at=self.now + timedelta(seconds=45)).status_code, 201)

    def test_heartbeat_extends_lease_but_sleep_or_disconnect_does_not_count_forever(self):
        session_id = self.post('work-start').data['session']['id']
        self.client.force_authenticate(self.a)
        with patch('django.utils.timezone.now', return_value=self.now + timedelta(seconds=60)):
            beat = self.client.post('/api/tasks/work-session/', {'session_id': session_id}, format='json')
        self.assertTrue(beat.data['session']['running'])
        with patch('django.utils.timezone.now', return_value=self.now + timedelta(hours=2)):
            result = self.client.post('/api/tasks/work-session/', {'session_id': session_id}, format='json')
            self.assertIsNone(result.data['session'])
            task = self.client.get(f'/api/tasks/{self.task.pk}/').data
        self.assertEqual(task['collaboration']['total_seconds'], 150)
        restarted = self.post('work-start', at=self.now + timedelta(hours=2))
        self.assertNotEqual(restarted.data['session']['id'], session_id)
        # A delayed old stop must not stop the new session.
        self.assertEqual(
            self.post('work-stop', {'session_id': session_id}, at=self.now + timedelta(hours=2)).data['session']['id'],
            restarted.data['session']['id'],
        )

    def test_completion_cancels_pending_request_and_stops_timer(self):
        self.post('work-start')
        request_id = self.request_transfer(self.b)
        self.client.force_authenticate(self.manager)
        with patch('django.utils.timezone.now', return_value=self.now + timedelta(seconds=20)):
            response = self.client.patch(f'/api/tasks/{self.task.pk}/', {'status': 'DONE'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(TaskWorkSession.objects.get().ended_at)
        self.assertEqual(TaskTransfer.objects.get().status, 'CANCELLED')
        self.assertEqual(self.post('work-start').status_code, 409)
        self.assertEqual(self.post('transfer-request', {'recipient': self.c.pk}).status_code, 409)
        self.assertNotEqual(self.accept(request_id, self.b).status_code, 200)

    def test_incoming_requests_visible_to_recipient_and_not_other_workers(self):
        self.request_transfer(self.b)
        self.client.force_authenticate(self.b)
        self.assertEqual(self.client.get('/api/tasks/').data['count'], 1)
        notices = self.client.get('/api/notifications/').data['items']
        self.assertEqual(notices[0]['kind'], 'task_transfer')
        self.client.force_authenticate(self.c)
        self.assertEqual(self.client.get('/api/tasks/').data['count'], 0)
        self.assertFalse(self.client.get('/api/notifications/').data['items'])

    def test_clients_cannot_submit_elapsed_seconds_or_impersonate_a_contributor(self):
        self.assertEqual(self.post('work-start', {'started_at': '2000-01-01'}).status_code, 400)
        self.assertEqual(
            self.post('progress', {'percent': 20, 'expected_percent': 0, 'employee': self.b.pk}).status_code, 400
        )
        self.assertEqual(self.post('work-start', user=self.manager).status_code, 403)
        self.assertFalse(TaskWorkSession.objects.exists())
        self.assertFalse(AuditEntry.objects.exists())
