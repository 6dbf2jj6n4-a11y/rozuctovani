import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_allocationkey_valid_from_optional"),
    ]

    operations = [
        migrations.CreateModel(
            name="CostEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14, verbose_name="Částka (Kč)")),
                ("note", models.CharField(blank=True, max_length=300, verbose_name="Poznámka")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cost_entries", to="core.period", verbose_name="Období")),
                ("service_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cost_entries", to="core.servicepoolitem", verbose_name="Položka zásobníku")),
            ],
            options={
                "verbose_name": "Náklad za období",
                "verbose_name_plural": "Náklady za období",
                "ordering": ["-period", "service_item"],
                "unique_together": {("service_item", "period")},
            },
        ),
        migrations.CreateModel(
            name="BillingLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14, verbose_name="Částka (Kč)")),
                ("share", models.DecimalField(blank=True, decimal_places=6, max_digits=8, null=True, verbose_name="Podíl")),
                ("calc_detail", models.JSONField(blank=True, default=dict, verbose_name="Detail výpočtu")),
                ("client_card", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="billing_lines", to="core.clientcard", verbose_name="Karta klienta")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="billing_lines", to="core.period", verbose_name="Období")),
                ("service_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="billing_lines", to="core.servicepoolitem", verbose_name="Položka zásobníku")),
            ],
            options={
                "verbose_name": "Vyúčtovaná položka",
                "verbose_name_plural": "Vyúčtované položky",
                "ordering": ["-period", "client_card", "service_item"],
                "unique_together": {("client_card", "period", "service_item")},
            },
        ),
        migrations.CreateModel(
            name="UnitService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("allocation_type", models.CharField(choices=[("percent", "Procento"), ("area_ratio", "Podle výměry (m²)"), ("person_count", "Podle počtu osob"), ("equal_split", "Rovným dílem"), ("submeter", "Podružné měřidlo (1:1)"), ("fixed_amount", "Pevná částka")], default="submeter", max_length=20, verbose_name="Typ rozpočtu")),
                ("value", models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True, verbose_name="Hodnota")),
                ("meter", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="unit_services", to="core.meter", verbose_name="Měřidlo")),
                ("service_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="unit_services", to="core.servicepoolitem", verbose_name="Služba")),
                ("unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="unit_services", to="core.unit", verbose_name="Plocha")),
            ],
            options={
                "verbose_name": "Výchozí služba plochy",
                "verbose_name_plural": "Výchozí služby plochy",
                "unique_together": {("unit", "service_item")},
            },
        ),
    ]
