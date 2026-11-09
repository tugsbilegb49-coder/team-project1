from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from .models import User


class ClientVersionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user('version-admin', role='ADMIN')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def save(self, **fields):
        version = self.client.get('/api/monitoring-settings/').data['version']
        return self.client.patch('/api/monitoring-settings/', {'expected_version': version, **fields}, format='json')

    def test_health_offers_the_newest_app_only_when_admin_published_one(self):
        self.assertNotIn('client', APIClient().get('/api/health/').data)
        link = 'https://github.com/example/worktrack/releases/latest'
        self.assertEqual(self.save(client_version='1.1.0', client_download_url=link).status_code, 200)
        self.assertEqual(APIClient().get('/api/health/').data['client'], {'version': '1.1.0', 'download_url': link})
        self.assertEqual(self.save(client_version='').status_code, 200)
        self.assertNotIn('client', APIClient().get('/api/health/').data)

    def test_bad_versions_and_links_are_refused(self):
        for fields in (
            {'client_version': '1.1.0'},  # No link yet.
            {'client_version': 'latest', 'client_download_url': 'https://x.mn/a.zip'},
            {'client_version': '1.1', 'client_download_url': 'javascript:alert(1)'},
            {'client_version': '1.1', 'client_download_url': 'ftp://x.mn/a.zip'},
        ):
            self.assertEqual(self.save(**fields).status_code, 400, fields)
