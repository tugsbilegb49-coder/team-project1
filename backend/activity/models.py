from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class ActivityEvent(models.Model):
    class State(models.TextChoices):
        WORKING = "WORKING", "Working"
        PHONE = "PHONE", "Phone"
        IDLE = "IDLE", "Idle"
        AWAY = "AWAY", "Away"

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity_events")
    device = models.ForeignKey(
        "users.Device", on_delete=models.SET_NULL, null=True, blank=True, related_name="camera_events"
    )
    timestamp = models.DateTimeField()
    state = models.CharField(max_length=10, choices=State.choices)
    duration_seconds = models.FloatField(validators=[MinValueValidator(0)])
    source_person_id = models.CharField(max_length=64, blank=True, default="")
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "timestamp", "state", "duration_seconds", "source_person_id"],
                name="unique_imported_activity_event",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee} {self.state} @ {self.timestamp}"


class ComputerActivity(models.Model):
    """A privacy-minimised foreground-application time segment from the desktop agent."""

    class Category(models.TextChoices):
        WORK = "WORK", "Work"
        COMMUNICATION = "COMMUNICATION", "Communication"
        BROWSER = "BROWSER", "Browser"
        OTHER = "OTHER", "Other"

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="computer_activities")
    device = models.ForeignKey(
        "users.Device", on_delete=models.SET_NULL, null=True, blank=True, related_name="computer_activities"
    )
    started_at = models.DateTimeField()
    duration_seconds = models.FloatField(validators=[MinValueValidator(0)])
    application = models.CharField(max_length=120)
    category = models.CharField(max_length=15, choices=Category.choices, default=Category.OTHER)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "started_at", "duration_seconds", "application", "category"],
                name="unique_computer_activity_segment",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee} - {self.application} ({self.duration_seconds:.0f}s)"

