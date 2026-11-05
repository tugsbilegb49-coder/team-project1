import uuid
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

SCORE_VALIDATORS = [MinValueValidator(0), MaxValueValidator(100)]

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        MANAGER = 'manager', 'Manager'
        EMPLOYEE = 'employee', 'Employee'
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.EMPLOYEE)

class Department(models.Model):
    name = models.CharField(max_length=120, unique=True)
    def __str__(self):
        return self.name

class Employee(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='employee')
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='employees')
    position = models.CharField(max_length=120, blank=True)
    expected_daily_minutes = models.PositiveIntegerField(default=480, validators=[MinValueValidator(1), MaxValueValidator(1440)])
    def __str__(self):
        return self.user.username

class Workstation(models.Model):
    code = models.CharField(max_length=80, unique=True)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='workstations')
    camera_id = models.CharField(max_length=80, blank=True)

class ConsentRecord(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='consents')
    activity_allowed = models.BooleanField(default=False)
    camera_allowed = models.BooleanField(default=False)
    recorded_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-recorded_at', '-id']

class Task(models.Model):
    class Status(models.TextChoices):
        TODO = 'todo', 'To do'
        IN_PROGRESS = 'in_progress', 'In progress'
        DONE = 'done', 'Done'
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='tasks')
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    started_at = models.DateTimeField()
    due_at = models.DateTimeField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.TODO)
    quality_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=SCORE_VALIDATORS)
    class Meta:
        ordering = ['-due_at', '-id']

class ComputerActivity(models.Model):
    event_id = models.UUIDField(default=uuid.uuid4, unique=True)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='activities')
    workstation = models.ForeignKey(Workstation, on_delete=models.PROTECT)
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField()
    application = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=[(x, x) for x in ['documents', 'data', 'development', 'design', 'crm', 'internal']])
    active_seconds = models.PositiveIntegerField()
    class Meta:
        ordering = ['-started_at', '-id']

class CameraObservation(models.Model):
    event_id = models.UUIDField(default=uuid.uuid4, unique=True)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='observations')
    workstation = models.ForeignKey(Workstation, on_delete=models.PROTECT)
    observed_at = models.DateTimeField(db_index=True)
    person_count = models.PositiveIntegerField(validators=[MaxValueValidator(1000)])
    confidence = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    class Meta:
        ordering = ['-observed_at', '-id']

class ProductivityScore(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='scores')
    date = models.DateField(db_index=True)
    t = models.DecimalField(max_digits=5, decimal_places=2)
    q = models.DecimalField(max_digits=5, decimal_places=2)
    d = models.DecimalField(max_digits=5, decimal_places=2)
    w = models.DecimalField(max_digits=5, decimal_places=2)
    p = models.DecimalField(max_digits=5, decimal_places=2)
    level = models.CharField(max_length=6, choices=[('Low', 'Low'), ('Medium', 'Medium'), ('High', 'High')])
    calculated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['employee', 'date'], name='unique_employee_score_date')]
        ordering = ['-date', 'employee_id']
