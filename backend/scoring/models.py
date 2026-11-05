from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ProductivityScore(models.Model):
    class Category(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="productivity_scores")
    date = models.DateField()
    task_completion = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    quality = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    deadline_completion = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    work_process = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    score = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    category = models.CharField(max_length=6, choices=Category.choices)
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "employee__username"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "date"], name="unique_daily_productivity_score"),
        ]

    def __str__(self) -> str:
        return f"{self.employee} - {self.date}: {self.score}"

