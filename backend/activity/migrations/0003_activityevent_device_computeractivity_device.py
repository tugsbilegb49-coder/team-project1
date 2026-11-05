import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("activity", "0002_computeractivity"),
        ("users", "0002_device"),
    ]

    operations = [
        migrations.AddField(
            model_name="activityevent",
            name="device",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="camera_events", to="users.device"),
        ),
        migrations.AddField(
            model_name="computeractivity",
            name="device",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="computer_activities", to="users.device"),
        ),
    ]
