import os
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from .models import AuditEntry, User

TOKEN = 'local-setup-token-0123456789abcdef'


class FirstRunTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def create(self, **changes):
        data = {
            'token': TOKEN,
            'username': 'boss',
            'password': 'Ulaanbaatar-2026!',
            'confirm_password': 'Ulaanbaatar-2026!',
            **changes,
        }
        return self.client.post('/api/setup/', data, format='json')

    def test_closed_unless_the_local_launcher_set_a_token(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('WORKTRACK_SETUP_TOKEN', None)
            self.assertEqual(self.client.get('/api/setup/').data, {'needs_admin': True, 'setup_available': False})
            self.assertEqual(self.create().status_code, 403)
        self.assertFalse(User.objects.exists())

    @patch.dict(os.environ, {'WORKTRACK_SETUP_TOKEN': TOKEN})
    def test_creates_one_admin_who_can_log_in(self):
        self.assertEqual(self.client.get('/api/setup/').data, {'needs_admin': True, 'setup_available': True})
        response = self.create()
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username='boss')
        self.assertTrue(user.is_superuser and user.is_staff and user.is_admin_role)
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(AuditEntry.objects.filter(action='first_admin_created', object_id=str(user.pk)).exists())
        login = self.client.post(
            '/api/auth/login/', {'username': 'boss', 'password': 'Ulaanbaatar-2026!'}, format='json'
        )
        self.assertEqual(login.status_code, 200)
        self.assertFalse(self.client.get('/api/setup/').data['needs_admin'])

    @patch.dict(os.environ, {'WORKTRACK_SETUP_TOKEN': TOKEN})
    def test_wrong_token_or_existing_admin_is_refused(self):
        self.assertEqual(self.create(token='guess').status_code, 403)
        User.objects.create_superuser('first', password='Another-pass-2026')
        response = self.create()
        self.assertEqual(response.status_code, 403)
        self.assertIn('аль хэдийн', response.data['detail'])
        self.assertFalse(User.objects.filter(username='boss').exists())

    @patch.dict(os.environ, {'WORKTRACK_SETUP_TOKEN': TOKEN})
    def test_weak_or_mismatched_passwords_and_bad_names_are_explained(self):
        cases = [
            ({'password': '12345678', 'confirm_password': '12345678'}, 'password'),
            ({'confirm_password': 'something-else-2026'}, 'confirm_password'),
            ({'username': 'has space'}, 'username'),
        ]
        for changes, field in cases:
            with self.subTest(field=field):
                response = self.create(**changes)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
        self.assertFalse(User.objects.exists())

    @patch.dict(os.environ, {'WORKTRACK_SETUP_TOKEN': TOKEN})
    def test_unknown_fields_are_rejected(self):
        self.assertEqual(self.create(is_superuser=False).status_code, 400)
