from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "departments"

    def __str__(self):
        return self.name


class Employee(models.Model):
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    full_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "employees"

    def __str__(self):
        return self.full_name


class Task(models.Model):
    STATUS_CHOICES = [
        ("todo", "Todo"),
        ("in_progress", "In progress"),
        ("done", "Done"),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="todo")
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "tasks"

    def __str__(self):
        return self.title


class ConsentRecord(models.Model):
    CONSENT_TYPES = [("computer", "Computer"), ("camera", "Camera")]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    consent_type = models.CharField(max_length=50, choices=CONSENT_TYPES)
    is_granted = models.BooleanField(default=False)
    granted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "consent_records"


class ComputerActivity(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    active_seconds = models.PositiveIntegerField(default=0)
    idle_seconds = models.PositiveIntegerField(default=0)
    key_count = models.PositiveIntegerField(default=0)
    click_count = models.PositiveIntegerField(default=0)
    app_name = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "computer_activities"
        indexes = [models.Index(fields=["employee", "date"])]


class CameraAnalytics(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    observed_at = models.DateTimeField()
    is_at_desk = models.BooleanField()
    confidence = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(1)]
    )

    class Meta:
        db_table = "camera_analytics"
        indexes = [models.Index(fields=["employee", "observed_at"])]
