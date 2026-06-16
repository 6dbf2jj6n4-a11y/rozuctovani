import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_initial"),
        ("meters", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServicePoolItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Název")),
                ("invoice_class", models.CharField(choices=[("rent", "Nájemné"), ("electricity", "Elektřina"), ("water", "Voda"), ("heat", "Teplo"), ("other", "Ostatní")], default="other", max_length=20, verbose_name="Třída")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_items", to="core.site", verbose_name="Areál")),
                ("unit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="service_items", to="core.unit", verbose_name="Prostor")),
                ("meter", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="service_items", to="meters.meter", verbose_name="Měřidlo")),
            ],
            options={"verbose_name": "Položka zásobníku", "verbose_name_plural": "Zásobník", "ordering": ["site", "invoice_class", "name"]},
        ),
        migrations.CreateModel(
            name="CostEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14, verbose_name="Částka (Kč)")),
                ("note", models.CharField(blank=True, max_length=300, verbose_name="Poznámka")),
                ("service_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cost_entries", to="billing.servicepoolitem", verbose_name="Položka zásobníku")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cost_entries", to="meters.period", verbose_name="Období")),
            ],
            options={"verbose_name": "Náklad za období", "verbose_name_plural": "Náklady za období", "ordering": ["-period", "service_item"], "unique_together": {("service_item", "period")}},
        ),
        migrations.CreateModel(
            name="AllocationKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("allocation_type", models.CharField(choices=[("percent", "Procento"), ("area_ratio", "Podle výměry (m²)"), ("person_count", "Podle počtu osob"), ("equal_split", "Rovným dílem"), ("submeter", "Podružné měřidlo (1:1)"), ("fixed_amount", "Pevná částka")], max_length=20, verbose_name="Typ rozpočtu")),
                ("value", models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True, verbose_name="Hodnota")),
                ("valid_from", models.DateField(verbose_name="Platnost od")),
                ("valid_to", models.DateField(blank=True, null=True, verbose_name="Platnost do")),
                ("client_card", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocation_keys", to="core.clientcard", verbose_name="Karta klienta")),
                ("service_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocation_keys", to="billing.servicepoolitem", verbose_name="Položka zásobníku")),
                ("meter", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="submeter_keys", to="meters.meter", verbose_name="Podružné měřidlo")),
            ],
            options={"verbose_name": "Klíč", "verbose_name_plural": "Klíče", "ordering": ["service_item", "client_card"]},
        ),
        migrations.CreateModel(
            name="BillingLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14, verbose_name="Částka (Kč)")),
                ("share", models.DecimalField(blank=True, decimal_places=6, max_digits=8, null=True, verbose_name="Podíl")),
                ("calc_detail", models.JSONField(blank=True, default=dict, verbose_name="Detail výpočtu")),
                ("client_card", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="billing_lines", to="core.clientcard", verbose_name="Karta klienta")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="billing_lines", to="meters.period", verbose_name="Období")),
                ("service_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="billing_lines", to="billing.servicepoolitem", verbose_name="Položka zásobníku")),
            ],
            options={"verbose_name": "Vyúčtovaná položka", "verbose_name_plural": "Vyúčtované položky", "ordering": ["-period", "client_card", "service_item"], "unique_together": {("client_card", "period", "service_item")}},
        ),
    ]
