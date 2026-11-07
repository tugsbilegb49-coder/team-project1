"""Exercise task/user row locks using independent PostgreSQL connections."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import connection, close_old_connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from users.models import Department, User
from .models import Task, TaskTransfer, TaskWorkSession


@skipUnless(connection.vendor == 'postgresql', 'Requires PostgreSQL row locks')
class TaskConcurrencyTests(TransactionTestCase):
    def setUp(self):
        department = Department.objects.create(name='Concurrent team')
        self.sender = User.objects.create_user('sender', department=department)
        self.recipient = User.objects.create_user('recipient', department=department)
        self.task = Task.objects.create(title='Concurrent work', employee=self.sender)

    def simultaneous(self, user, requests):
        barrier = Barrier(2)
        def submit(item):
            close_old_connections()
            try:
                client = APIClient(); client.force_authenticate(user)
                barrier.wait(timeout=5)
                return client.post(item[0], item[1], format='json').status_code
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(submit, item) for item in requests]
            return sorted(future.result(timeout=10) for future in futures)

    def test_duplicate_acceptance_consumes_only_one_transfer(self):
        transfer = TaskTransfer.objects.create(task=self.task, from_employee=self.sender, to_employee=self.recipient,
            requested_by=self.sender, from_name='sender', to_name='recipient')
        item = (f'/api/tasks/{self.task.pk}/transfer-respond/', {'request_id':transfer.pk, 'decision':'accept'})
        self.assertEqual(self.simultaneous(self.recipient, [item, item]), [200, 409])
        self.task.refresh_from_db()
        self.assertEqual(self.task.transfer_count, 1)

    def test_two_simultaneous_work_starts_cannot_overlap_for_one_person(self):
        other = Task.objects.create(title='Other', employee=self.sender)
        requests = [(f'/api/tasks/{task.pk}/work-start/', {}) for task in (self.task, other)]
        self.assertEqual(self.simultaneous(self.sender, requests), [201, 409])
        self.assertEqual(TaskWorkSession.objects.filter(ended_at__isnull=True).count(), 1)

    def test_only_one_pending_request_can_be_created_concurrently(self):
        item = (f'/api/tasks/{self.task.pk}/transfer-request/', {'recipient':self.recipient.pk})
        self.assertEqual(self.simultaneous(self.sender, [item, item]), [200, 409])
        self.assertEqual(TaskTransfer.objects.filter(status='PENDING').count(), 1)
