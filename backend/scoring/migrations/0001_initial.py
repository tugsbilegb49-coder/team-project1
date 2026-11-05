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
            name="ProductivityScore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("task_completion", models.DecimalField(decimal_places=2, max_digits=5, validators=[MinValueValidator(0), MaxValueValidator(100)])),
                ("quality", models.DecimalField(decimal_places=2, max_digits=5, validators=[MinValueValidator(0), MaxValueValidator(100)])),
                ("deadline_completion", models.DecimalField(decimal_places=2, max_digits=5, validators=[MinValueValidator(0), MaxValueValidator(100)])),
                ("work_process", models.DecimalField(decimal_places=2, max_digits=5, validators=[MinValueValidator(0), MaxValueValidator(100)])),
                ("score", models.DecimalField(decimal_places=2, max_digits=5, validators=[MinValueValidator(0), MaxValueValidator(100)])),
                ("category", models.CharField(choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High")], max_length=6)),
                ("calculated_at", models.DateTimeField(auto_now=True)),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="productivity_scores", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-date", "employee__username"]},
        ),
        migrations.AddConstraint(
            model_name="productivityscore",
            constraint=models.UniqueConstraint(fields=("employee", "date"), name="unique_daily_productivity_score"),
        ),
    ]
