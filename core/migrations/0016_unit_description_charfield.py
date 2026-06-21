from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_unitservice_state_only"),
    ]

    operations = [
        migrations.AlterField(
            model_name="unit",
            name="description",
            field=models.CharField(blank=True, max_length=300, verbose_name="Popis"),
        ),
    ]
