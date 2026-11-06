from django.test import TestCase
from rest_framework.test import APIClient

from .models import Department, User


class AuthenticationAndRoleTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.department = Department.objects.create(name="Engineering")
        self.employee = User.objects.create_user(
            username="employee",
            password="safe-password-123",
            department=self.department,
            role=User.Role.EMPLOYEE,
        )
        self.colleague = User.objects.create_user(
            username="colleague",
            password="safe-password-123",
            department=self.department,
            role=User.Role.EMPLOYEE,
        )

    def test_login_returns_jwt_tokens(self):
        client = APIClient()
        response = client.post(
            "/api/auth/login/",
            {"username": "employee", "password": "safe-password-123"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_employee_can_only_see_own_user_record(self):
        client = APIClient()
        client.force_authenticate(self.employee)
        response = client.get("/api/users/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["username"], "employee")

    def test_employee_can_grant_and_revoke_monitoring_consent(self):
        client = APIClient()
        client.force_authenticate(self.employee)
        granted = client.post("/api/consents/grant/", {"policy_version": "2026-11"}, format="json")
        self.assertEqual(granted.status_code, 201)
        self.assertTrue(granted.data["is_active"])
        self.assertTrue(client.get("/api/consents/status/").data["active"])
        revoked = client.post("/api/consents/revoke/", {}, format="json")
        self.assertEqual(revoked.data["revoked"], 1)
        self.assertFalse(client.get("/api/consents/status/").data["active"])

    def test_login_can_enroll_own_device(self):
        client = APIClient()
        client.force_authenticate(self.employee)
        response = client.post(
            "/api/devices/enroll/",
            {"name": "Test laptop", "platform": "Darwin"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["employee"], self.employee.pk)



class LoginProtectionTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user=User.objects.create_user('protected-worker',password='strong-login-password-123')
        self.other=User.objects.create_user('other-login',password='strong-login-password-123')
        self.client=APIClient()

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def login(self, username='protected-worker', **kwargs):
        return self.client.post('/api/auth/login/',{'username':username,'password':'strong-login-password-123'},format='json',**kwargs)

    def test_ip_limit_returns_429_and_retry_after(self):
        from .auth import LoginIPThrottle
        from unittest.mock import patch
        with patch.object(LoginIPThrottle,'rate','2/min',create=True):
            self.assertEqual(self.login().status_code,200)
            self.assertEqual(self.login().status_code,200)
            response=self.login()
        self.assertEqual(response.status_code,429)
        self.assertGreater(int(response['Retry-After']),0)

    def test_failed_password_attempts_are_limited_and_fake_forwarded_ip_cannot_bypass(self):
        from .auth import LoginIPThrottle
        from unittest.mock import patch
        with patch.object(LoginIPThrottle,'rate','1/min',create=True):
            first=self.client.post('/api/auth/login/',{'username':self.user.username,'password':'incorrect'},format='json',HTTP_X_FORWARDED_FOR='1.2.3.4')
            second=self.login(HTTP_X_FORWARDED_FOR='5.6.7.8')
        self.assertEqual(first.status_code,401)
        self.assertEqual(second.status_code,429)

    def test_account_limit_applies_across_different_ips(self):
        from .auth import LoginAccountThrottle
        from unittest.mock import patch
        with patch.object(LoginAccountThrottle,'rate','1/min',create=True):
            self.assertEqual(self.login(REMOTE_ADDR='10.0.0.1').status_code,200)
            self.assertEqual(self.login(REMOTE_ADDR='10.0.0.2').status_code,429)
            self.assertEqual(self.login(username='other-login',REMOTE_ADDR='10.0.0.2').status_code,200)

    def test_logout_revokes_refresh_but_does_not_pretend_access_is_revoked(self):
        tokens=self.login().data
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+tokens['access'])
        response=self.client.post('/api/auth/logout/',{'refresh':tokens['refresh']},format='json')
        self.assertEqual(response.status_code,204)
        self.assertEqual(self.client.get('/api/users/me/').status_code,200)
        self.client.credentials()
        self.assertEqual(self.client.post('/api/auth/refresh/',{'refresh':tokens['refresh']},format='json').status_code,401)

    def test_other_user_cannot_revoke_owners_token(self):
        own=self.login().data
        other=self.login('other-login').data
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+own['access'])
        self.assertEqual(self.client.post('/api/auth/logout/',{'refresh':other['refresh']},format='json').status_code,403)
        self.client.credentials()
        self.assertEqual(self.client.post('/api/auth/refresh/',{'refresh':other['refresh']},format='json').status_code,200)

    def test_logout_requires_authentication_and_rejects_invalid_input(self):
        self.assertEqual(self.client.post('/api/auth/logout/',{},format='json').status_code,401)
        self.client.force_authenticate(self.user)
        for data in ({},{'refresh':'not-a-token'}):
            self.assertEqual(self.client.post('/api/auth/logout/',data,format='json').status_code,400)

    def test_ip_limit_allows_login_again_after_window(self):
        from .auth import LoginIPThrottle
        from unittest.mock import patch
        with patch.object(LoginIPThrottle,'rate','1/min',create=True), patch.object(LoginIPThrottle,'timer',return_value=100):
            self.assertEqual(self.login().status_code,200)
            self.assertEqual(self.login().status_code,429)
        with patch.object(LoginIPThrottle,'rate','1/min',create=True), patch.object(LoginIPThrottle,'timer',return_value=161):
            self.assertEqual(self.login().status_code,200)
