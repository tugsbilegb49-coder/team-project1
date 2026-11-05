from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("activity", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ComputerActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField()),
                ("duration_seconds", models.FloatField(validators=[MinValueValidator(0)])),
                ("application", models.CharField(max_length=120)),
                ("category", models.CharField(choices=[("WORK", "Work"), ("COMMUNICATION", "Communication"), ("BROWSER", "Browser"), ("OTHER", "Other")], default="OTHER", max_length=15)),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="computer_activities", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.AddConstraint(
            model_name="computeractivity",
            constraint=models.UniqueConstraint(fields=("employee", "started_at", "duration_seconds", "application", "category"), name="unique_computer_activity_segment"),
        ),
    ]
