from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_allocationkey_weighted_count"),
    ]

    operations = [
        migrations.AlterField(
            model_name="servicepoolitem",
            name="default_allocation_type",
            field=models.CharField(
                verbose_name="Výchozí typ rozpočtu",
                max_length=20,
                blank=True,
                choices=[
                    ("percent", "Procento"),
                    ("area_ratio", "Podle výměry (m²)"),
                    ("person_count", "Podle počtu osob"),
                    ("equal_split", "Rovným dílem"),
                    ("submeter", "Podružné měřidlo (1:1)"),
                    ("fixed_amount", "Pevná částka"),
                    ("weighted_count", "Podle váhy (počet jednotek)"),
                ],
                help_text=(
                    "Predvyplni se pri zalozeni noveho klice na karte klienta "
                    "pro tuto polozku."
                ),
            ),
        ),
    ]
