"""Real PostgreSQL checks for the per-employee ingestion lock."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless

from django.db import connection, close_old_connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import User
from .models import ComputerActivity


@skipUnless(connection.vendor == 'postgresql', 'Requires a real PostgreSQL server')
@override_settings(REQUIRE_MONITORING_CONSENT=False)
class PostgreSQLConcurrentIngestTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user('concurrent-worker')
        self.start = timezone.now() - timedelta(seconds=60)

    def simultaneous(self, applications):
        barrier = Barrier(2)

        def ingest(application):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(self.user)
                barrier.wait(timeout=5)
                response = client.post(
                    '/api/computer-activity/ingest/',
                    {
                        'started_at': self.start.isoformat(),
                        'duration_seconds': 30,
                        'application': application,
                        'category': 'WORK',
                    },
                    format='json',
                )
                return response.status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(ingest, app) for app in applications]
            return sorted(future.result(timeout=10) for future in futures)

    def test_overlapping_concurrent_requests_cannot_both_write(self):
        self.assertEqual(self.simultaneous(['Code', 'Safari']), [201, 400])
        self.assertEqual(ComputerActivity.objects.count(), 1)

    def test_simultaneous_identical_retries_are_idempotent(self):
        self.assertEqual(self.simultaneous(['Code', 'Code']), [200, 201])
        self.assertEqual(ComputerActivity.objects.count(), 1)
