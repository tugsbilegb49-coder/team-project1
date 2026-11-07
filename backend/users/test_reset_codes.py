from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AuditEntry, PasswordResetCode, User

NEW = 'Fresh-worktrack-pass-48!'


class ResetCodeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user('codes-admin', role='ADMIN', password='Admin-pass-xyz-913!')
        self.worker = User.objects.create_user('codes-worker', password='Forgotten-pass-772!')
        self.manager = User.objects.create_user('codes-manager', role='MANAGER')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def issue(self, user=None):
        return self.client.post(f'/api/users/{(user or self.worker).pk}/reset-code/')

    def reset(self, code, password=NEW, username='codes-worker', confirm=None):
        return APIClient().post(
            '/api/auth/reset-password/',
            {'username': username, 'code': code, 'new_password': password, 'confirm_password': confirm or password},
            format='json',
        )

    def test_employee_sets_a_new_password_with_the_admins_code_once(self):
        session = RefreshToken.for_user(self.worker)
        response = self.issue()
        self.assertEqual(response.status_code, 201)
        code = response.data['code']
        self.assertRegex(code, r'^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$')
        self.assertNotIn(code.replace('-', ''), str(PasswordResetCode.objects.values_list('code_hash', flat=True)))
        self.assertEqual(self.reset(' ' + code.lower().replace('-', ' ') + ' ').status_code, 200)
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.check_password(NEW))
        refreshed = APIClient().post('/api/auth/refresh/', {'refresh': str(session)}, format='json')
        self.assertEqual(refreshed.status_code, 401)  # Old sessions end.
        self.assertEqual(self.reset(code, 'Another-pass-value-61!').status_code, 400)  # Used up.
        actions = set(AuditEntry.objects.filter(employee=self.worker).values_list('action', flat=True))
        self.assertTrue({'password_reset_code', 'password_reset'} <= actions)

    def test_wrong_old_or_replaced_codes_and_wrong_users_fail_the_same_way(self):
        first = self.issue().data['code']
        second = self.issue().data['code']
        self.assertEqual(self.reset(first).data['code'][0], self.reset('ABCD-EFGH-JKLM').data['code'][0])
        self.assertEqual(self.reset(second, username='codes-admin').status_code, 400)
        with patch('users.reset_codes.timezone.now', return_value=timezone.now() + timedelta(hours=25)):
            self.assertEqual(self.reset(second).status_code, 400)
        self.assertEqual(self.reset(second).status_code, 200)

    def test_weak_or_mismatched_new_passwords_keep_the_code(self):
        code = self.issue().data['code']
        self.assertIn('new_password', self.reset(code, 'password').data)
        self.assertIn('confirm_password', self.reset(code, NEW, confirm=NEW + 'x').data)
        self.assertEqual(self.reset(code).status_code, 200)

    def test_only_admins_issue_codes_and_not_for_inactive_people(self):
        for person in (self.manager, self.worker):
            self.client.force_authenticate(person)
            self.assertEqual(self.issue().status_code, 403)
        self.client.force_authenticate(self.admin)
        self.worker.is_active = False
        self.worker.save()
        self.assertEqual(self.issue().status_code, 400)

    def test_guessing_is_throttled_like_login(self):
        self.issue()
        statuses = [self.reset(f'AAAA-BBBB-{i:04d}').status_code for i in range(12)]
        self.assertIn(429, statuses)
