from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models
import uuid


class Department(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        MANAGER = 'MANAGER', 'Manager'
        EMPLOYEE = 'EMPLOYEE', 'Employee'

    role = models.CharField(max_length=12, choices=Role.choices, default=Role.EMPLOYEE)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='members',
    )

    @property
    def is_admin_role(self) -> bool:
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def is_manager(self) -> bool:
        return self.role == self.Role.MANAGER


class ConsentRecord(models.Model):
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='consents')
    granted = models.BooleanField(default=False)
    policy_version = models.CharField(max_length=40)
    recorded_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-recorded_at']

    @property
    def is_active(self) -> bool:
        return self.granted and self.revoked_at is None


class Device(models.Model):
    """A user-approved workstation running the local monitoring agent."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='devices')
    name = models.CharField(max_length=120)
    platform = models.CharField(max_length=40)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['employee', 'name'], name='unique_employee_device_name'),
        ]

    def __str__(self) -> str:
        return f'{self.employee} - {self.name}'


def default_productive_apps():
    return list(getattr(settings, 'PRODUCTIVE_APPLICATIONS', []))


class MonitoringSettings(models.Model):
    productive_apps = models.JSONField(default=default_productive_apps)
    camera_threshold = models.FloatField(default=0.45)
    presence_log_max_bytes = models.PositiveIntegerField(default=5242880)
    presence_log_backups = models.PositiveSmallIntegerField(default=3)
    presence_log_retention_days = models.PositiveSmallIntegerField(default=7)
    activity_retention_days = models.PositiveSmallIntegerField(default=90)
    automatic_retention = models.BooleanField(default=False)
    # The newest employee app the admin wants everyone on; older apps show where to download it.
    client_version = models.CharField(max_length=20, blank=True)
    client_download_url = models.URLField(max_length=500, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )


class AgentHeartbeat(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='heartbeats')
    kind = models.CharField(max_length=20, default='computer')
    seen_at = models.DateTimeField()
    queue_count = models.PositiveIntegerField(default=0)
    paused = models.BooleanField(default=False)
    last_upload_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=24, blank=True)
    agent_version = models.CharField(max_length=40, blank=True)
    settings_version = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['device', 'kind'], name='one_heartbeat_per_device_kind')]


class AuditEntry(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='audit_actions'
    )
    actor_label = models.CharField(max_length=150)
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='audit_entries'
    )
    action = models.CharField(max_length=30)
    resource = models.CharField(max_length=40)
    object_id = models.CharField(max_length=64)
    changes = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']


class LauncherInterval(models.Model):
    """Client-observed awake launcher time, not a measure of productive work."""

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='launcher_intervals')
    device = models.ForeignKey(Device, null=True, on_delete=models.SET_NULL, related_name='launcher_intervals')
    event_id = models.UUIDField()
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(db_index=True)
    received_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['employee', 'event_id'], name='unique_employee_launcher_interval'),
            models.CheckConstraint(
                condition=models.Q(ended_at__gte=models.F('started_at')), name='launcher_interval_order'
            ),
        ]


class PasswordResetCode(models.Model):
    """A one-time code an admin gives an employee who forgot their password (no e-mail needed).

    Only a hash is stored. The code works once, for one day, and a newer code replaces older ones.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reset_codes')
    code_hash = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='issued_reset_codes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
