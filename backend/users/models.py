from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models
import uuid


class Department(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        MANAGER = "MANAGER", "Manager"
        EMPLOYEE = "EMPLOYEE", "Employee"

    role = models.CharField(max_length=12, choices=Role.choices, default=Role.EMPLOYEE)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )

    @property
    def is_admin_role(self) -> bool:
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def is_manager(self) -> bool:
        return self.role == self.Role.MANAGER


class ConsentRecord(models.Model):
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consents")
    granted = models.BooleanField(default=False)
    policy_version = models.CharField(max_length=40)
    recorded_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-recorded_at"]

    @property
    def is_active(self) -> bool:
        return self.granted and self.revoked_at is None


class Device(models.Model):
    """A user-approved workstation running the local monitoring agent."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="devices")
    name = models.CharField(max_length=120)
    platform = models.CharField(max_length=40)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "name"], name="unique_employee_device_name"),
        ]

    def __str__(self) -> str:
        return f"{self.employee} - {self.name}"

