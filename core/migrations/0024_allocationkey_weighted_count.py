from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_meter_reading_mode"),
    ]

    operations = [
        migrations.AlterField(
            model_name="allocationkey",
            name="allocation_type",
            field=models.CharField(
                verbose_name="Typ rozpočtu",
                max_length=20,
                choices=[
                    ("percent", "Procento"),
                    ("area_ratio", "Podle výměry (m²)"),
                    ("person_count", "Podle počtu osob"),
                    ("equal_split", "Rovným dílem"),
                    ("submeter", "Podružné měřidlo (1:1)"),
                    ("fixed_amount", "Pevná částka"),
                    ("weighted_count", "Podle váhy (počet jednotek)"),
                ],
            ),
        ),
    ]
