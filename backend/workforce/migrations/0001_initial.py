from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Task",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("TODO", "To do"), ("IN_PROGRESS", "In progress"), ("DONE", "Done")], default="TODO", max_length=15)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("quality_score", models.DecimalField(blank=True, decimal_places=2, help_text="Manager assessment from 0 to 100.", max_digits=5, null=True, validators=[MinValueValidator(0), MaxValueValidator(100)])),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assigned_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_tasks", to=settings.AUTH_USER_MODEL)),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tasks", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["due_date", "-created_at"]},
        ),
    ]
