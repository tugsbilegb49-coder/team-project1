from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ActivityEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timestamp", models.DateTimeField()),
                ("state", models.CharField(choices=[("WORKING", "Working"), ("PHONE", "Phone"), ("IDLE", "Idle"), ("AWAY", "Away")], max_length=10)),
                ("duration_seconds", models.FloatField(validators=[MinValueValidator(0)])),
                ("source_person_id", models.CharField(blank=True, default="", max_length=64)),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activity_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-timestamp"]},
        ),
        migrations.AddConstraint(
            model_name="activityevent",
            constraint=models.UniqueConstraint(fields=("employee", "timestamp", "state", "duration_seconds", "source_person_id"), name="unique_imported_activity_event"),
        ),
    ]
