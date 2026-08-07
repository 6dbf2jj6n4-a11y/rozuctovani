from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0048_remove_client_note"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="meterreading",
            name="is_estimate",
        ),
    ]
