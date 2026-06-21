from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_cardunit_area_override"),
    ]

    operations = [
        migrations.AddField(
            model_name="meter",
            name="code",
            field=models.CharField(blank=True, max_length=50, verbose_name="Kód"),
        ),
        migrations.AddField(
            model_name="meter",
            name="is_virtual",
            field=models.BooleanField(default=False, verbose_name="Virtuální (vypočtené)"),
        ),
        migrations.AddField(
            model_name="meter",
            name="formula",
            field=models.CharField(blank=True, max_length=300, verbose_name="Vzorec"),
        ),
        migrations.AddField(
            model_name="servicepoolitem",
            name="default_allocation_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("percent", "Procento"),
                    ("area_ratio", "Podle výměry (m²)"),
                    ("person_count", "Podle počtu osob"),
                    ("equal_split", "Rovným dílem"),
                    ("submeter", "Podružné měřidlo (1:1)"),
                    ("fixed_amount", "Pevná částka"),
                ],
                max_length=20,
                verbose_name="Výchozí typ rozpočtu",
            ),
        ),
    ]
