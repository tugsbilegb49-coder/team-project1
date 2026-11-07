from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from workforce.models import Task
from .models import AuditEntry, Department, User


class AdminPasswordResetTests(TestCase):
    old_password = 'Previous-worktrack-931!'
    new_password = '  Updated-worktrack-572!  '

    @classmethod
    def setUpTestData(cls):
        department = Department.objects.create(name='Password reset team')
        cls.admin = User.objects.create_user('reset-admin', role='ADMIN', password=cls.old_password)
        cls.worker = User.objects.create_user('reset-worker', department=department, password=cls.old_password)
        cls.manager = User.objects.create_user('reset-manager', role='MANAGER', department=department)
        cls.task = Task.objects.create(employee=cls.worker, title='Keep this assignment')

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin_token = RefreshToken.for_user(self.admin)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+str(self.admin_token.access_token))
        self.worker_tokens = [RefreshToken.for_user(self.worker), RefreshToken.for_user(self.worker)]
        self.path = f'/api/users/{self.worker.pk}/'

    def test_admin_reset_preserves_account_and_tasks_and_revokes_worker_sessions(self):
        response = self.client.patch(self.path, {'password': self.new_password}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('password', response.data)
        self.assertEqual(response.data['username'], self.worker.username)
        self.assertEqual(response.data['id'], self.worker.pk)
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.check_password(self.new_password))
        self.assertFalse(self.worker.check_password(self.new_password.strip()))
        self.assertEqual(Task.objects.get(pk=self.task.pk).employee_id, self.worker.pk)
        for token in self.worker_tokens:
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION='Bearer '+str(token.access_token))
            self.assertEqual(client.get('/api/users/me/').status_code, 401)
            self.assertEqual(APIClient().post('/api/auth/refresh/', {'refresh': str(token)}, format='json').status_code, 401)
        self.assertEqual(self.client.get('/api/users/me/').status_code, 200)
        self.assertEqual(APIClient().post('/api/auth/refresh/', {'refresh': str(self.admin_token)}, format='json').status_code, 200)
        login = APIClient()
        self.assertEqual(login.post('/api/auth/login/', {'username': self.worker.username, 'password': self.old_password}, format='json').status_code, 401)
        self.assertEqual(login.post('/api/auth/login/', {'username': self.worker.username, 'password': self.new_password}, format='json').status_code, 200)
        audit = AuditEntry.objects.get(action='password_change')
        self.assertEqual(audit.actor_id, self.admin.pk)
        self.assertEqual(audit.object_id, str(self.worker.pk))
        self.assertEqual(audit.changes, {})

    def test_employee_and_manager_cannot_reset_even_their_own_password_through_admin_api(self):
        for actor in (self.worker, self.manager):
            self.client.force_authenticate(actor)
            for target in (self.worker, actor, self.admin):
                with self.subTest(actor=actor.role, target=target.username):
                    self.assertEqual(self.client.patch(f'/api/users/{target.pk}/', {'password': self.new_password}, format='json').status_code, 403)
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.check_password(self.old_password))
        self.assertFalse(AuditEntry.objects.exists())

    def test_unauthenticated_reset_is_rejected(self):
        self.assertEqual(APIClient().patch(self.path, {'password': self.new_password}, format='json').status_code, 401)

    def test_invalid_password_does_not_change_account_or_revoke_tokens(self):
        for password in ('', 'short', '12345678', 'x'*257):
            with self.subTest(password_length=len(password)):
                self.assertEqual(self.client.patch(self.path, {'password': password}, format='json').status_code, 400)
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.check_password(self.old_password))
        self.assertFalse(AuditEntry.objects.exists())
        self.assertEqual(APIClient().post('/api/auth/refresh/', {'refresh': str(self.worker_tokens[0])}, format='json').status_code, 200)

    def test_profile_update_does_not_revoke_sessions(self):
        self.assertEqual(self.client.patch(self.path, {'first_name': 'Updated name'}, format='json').status_code, 200)
        self.assertEqual(APIClient().post('/api/auth/refresh/', {'refresh': str(self.worker_tokens[0])}, format='json').status_code, 200)
        self.assertFalse(AuditEntry.objects.filter(action='password_change').exists())

    def test_superuser_without_admin_role_can_reset(self):
        superuser = User.objects.create_superuser('reset-superuser', password=self.old_password, role='EMPLOYEE')
        self.client.force_authenticate(superuser)
        self.assertEqual(self.client.patch(self.path, {'password': self.new_password}, format='json').status_code, 200)
