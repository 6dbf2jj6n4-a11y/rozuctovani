from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_unitservice"),
    ]

    operations = [
        migrations.AddField(
            model_name="cardunit",
            name="area_m2_override",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True,
                verbose_name="Výměra (m²) - úprava"
            ),
        ),
    ]
