from django.test import TestCase
from rest_framework.test import APIClient

from .models import Department, User


class AuthenticationAndRoleTests(TestCase):
    def setUp(self):
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

