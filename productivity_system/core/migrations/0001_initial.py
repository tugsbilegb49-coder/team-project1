# Generated as the initial schema for the core app.
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Department",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100, unique=True)),
            ],
            options={"db_table": "departments"},
        ),
        migrations.CreateModel(
            name="Employee",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("full_name", models.CharField(max_length=150)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="core.department",
                    ),
                ),
            ],
            options={"db_table": "employees"},
        ),
        migrations.CreateModel(
            name="Task",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(max_length=200),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("todo", "Todo"),
                            ("in_progress", "In progress"),
                            ("done", "Done"),
                        ],
                        default="todo",
                        max_length=20,
                    ),
                ),
                ("due_date", models.DateField(blank=True, null=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="core.employee",
                    ),
                ),
            ],
            options={"db_table": "tasks"},
        ),
        migrations.CreateModel(
            name="ConsentRecord",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "consent_type",
                    models.CharField(
                        choices=[("computer", "Computer"), ("camera", "Camera")],
                        max_length=50,
                    ),
                ),
                ("is_granted", models.BooleanField(default=False)),
                ("granted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="core.employee",
                    ),
                ),
            ],
            options={"db_table": "consent_records"},
        ),
        migrations.CreateModel(
            name="ComputerActivity",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("date", models.DateField()),
                ("active_seconds", models.PositiveIntegerField(default=0)),
                ("idle_seconds", models.PositiveIntegerField(default=0)),
                ("key_count", models.PositiveIntegerField(default=0)),
                ("click_count", models.PositiveIntegerField(default=0)),
                ("app_name", models.CharField(blank=True, max_length=100)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="core.employee",
                    ),
                ),
            ],
            options={"db_table": "computer_activities"},
        ),
        migrations.CreateModel(
            name="CameraAnalytics",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("observed_at", models.DateTimeField()),
                ("is_at_desk", models.BooleanField()),
                (
                    "confidence",
                    models.FloatField(
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(1),
                        ]
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="core.employee",
                    ),
                ),
            ],
            options={"db_table": "camera_analytics"},
        ),
        migrations.AddIndex(
            model_name="computeractivity",
            index=models.Index(
                fields=["employee", "date"], name="core_comp_emp_date_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="cameraanalytics",
            index=models.Index(
                fields=["employee", "observed_at"], name="core_cam_emp_time_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="task",
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=["todo", "in_progress", "done"]),
                name="task_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="consentrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(consent_type__in=["computer", "camera"]),
                name="consent_type_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="cameraanalytics",
            constraint=models.CheckConstraint(
                condition=models.Q(confidence__gte=0, confidence__lte=1),
                name="camera_confidence_valid",
            ),
        ),
    ]
