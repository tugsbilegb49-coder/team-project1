from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = 'TODO', 'To do'
        IN_PROGRESS = 'IN_PROGRESS', 'In progress'
        DONE = 'DONE', 'Done'

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tasks')
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.TODO)
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    quality_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Manager assessment from 0 to 100.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    transfer_count = models.PositiveSmallIntegerField(default=0, editable=False)

    class Meta:
        ordering = ['due_date', '-created_at']
        constraints = [models.CheckConstraint(condition=models.Q(transfer_count__lte=2), name='task_max_two_transfers')]

    def __str__(self) -> str:
        return self.title


class TaskContribution(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='contributions')
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='task_contributions'
    )
    employee_name = models.CharField(max_length=150)
    percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['task', 'employee'], name='unique_task_contributor'),
            models.CheckConstraint(
                condition=models.Q(percent__gte=0, percent__lte=100), name='task_contribution_percent_range'
            ),
        ]


class TaskWorkSession(models.Model):
    contribution = models.ForeignKey(TaskContribution, on_delete=models.CASCADE, related_name='sessions')
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='task_work_sessions'
    )
    started_at = models.DateTimeField()
    last_heartbeat = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['employee'], condition=models.Q(ended_at__isnull=True), name='one_running_task_per_employee'
            ),
            models.CheckConstraint(
                condition=models.Q(ended_at__isnull=True) | models.Q(ended_at__gte=models.F('started_at')),
                name='task_work_end_after_start',
            ),
        ]


class TaskTransfer(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        DECLINED = 'DECLINED', 'Declined'
        CANCELLED = 'CANCELLED', 'Cancelled'

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='transfers')
    from_employee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    to_employee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    from_name = models.CharField(max_length=150)
    to_name = models.CharField(max_length=150)
    note = models.CharField(max_length=1000, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['task'], condition=models.Q(status='PENDING'), name='one_pending_task_transfer'
            )
        ]
