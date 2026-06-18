from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_cardunit"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientcard",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="Aktivní"),
        ),
    ]
