import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_cardunit_rate"),
    ]

    operations = [
        migrations.CreateModel(
            name="UnitService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("allocation_type", models.CharField(choices=[("percent", "Procento"), ("area_ratio", "Podle výměry (m²)"), ("person_count", "Podle počtu osob"), ("equal_split", "Rovným dílem"), ("submeter", "Podružné měřidlo (1:1)"), ("fixed_amount", "Pevná částka")], default="submeter", max_length=20, verbose_name="Typ rozpočtu")),
                ("value", models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True, verbose_name="Hodnota")),
                ("unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="unit_services", to="core.unit", verbose_name="Plocha")),
                ("service_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="unit_services", to="core.servicepoolitem", verbose_name="Služba")),
                ("meter", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="unit_services", to="core.meter", verbose_name="Měřidlo")),
            ],
            options={"verbose_name": "Výchozí služba plochy", "verbose_name_plural": "Výchozí služby plochy", "unique_together": {("unit", "service_item")}},
        ),
    ]
