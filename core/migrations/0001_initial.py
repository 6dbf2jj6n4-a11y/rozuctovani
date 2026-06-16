import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="Site",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Nazev")),
                ("address", models.CharField(blank=True, max_length=300, verbose_name="Adresa")),
            ],
            options={"verbose_name": "Areál / objekt", "verbose_name_plural": "Areály / objekty", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Client",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Název / jméno")),
                ("ico", models.CharField(blank=True, max_length=20, verbose_name="IČO")),
                ("dic", models.CharField(blank=True, max_length=20, verbose_name="DIČ")),
                ("contact_email", models.EmailField(blank=True, max_length=254, verbose_name="E-mail")),
                ("contact_phone", models.CharField(blank=True, max_length=50, verbose_name="Telefon")),
                ("note", models.TextField(blank=True, verbose_name="Poznámka")),
            ],
            options={"verbose_name": "Klient", "verbose_name_plural": "Klienti", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Unit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Název / označení")),
                ("area_m2", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name="Výměra (m²)")),
                ("description", models.TextField(blank=True, verbose_name="Popis")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="units", to="core.site", verbose_name="Areál")),
            ],
            options={"verbose_name": "Pronajímaný prostor", "verbose_name_plural": "Pronajímané prostory", "ordering": ["site", "name"]},
        ),
        migrations.CreateModel(
            name="ClientCard",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("valid_from", models.DateField(verbose_name="Platnost od")),
                ("valid_to", models.DateField(blank=True, null=True, verbose_name="Platnost do")),
                ("note", models.TextField(blank=True, verbose_name="Poznámka")),
                ("client", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cards", to="core.client", verbose_name="Klient")),
                ("unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cards", to="core.unit", verbose_name="Prostor")),
            ],
            options={"verbose_name": "Karta klienta", "verbose_name_plural": "Karty klientů", "ordering": ["client", "valid_from"]},
        ),
        migrations.CreateModel(
            name="Meter",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Název / označení")),
                ("meter_type", models.CharField(choices=[("electricity", "Elektřina"), ("water", "Voda"), ("gas", "Plyn"), ("heat", "Teplo"), ("other", "Jiné")], max_length=20, verbose_name="Typ")),
                ("unit_of_measure", models.CharField(default="kWh", max_length=20, verbose_name="Měrná jednotka")),
                ("serial_number", models.CharField(blank=True, max_length=100, verbose_name="Výrobní číslo")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meters", to="core.site", verbose_name="Areál")),
                ("parent_meter", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="children", to="core.meter", verbose_name="Nadřazené měřidlo")),
            ],
            options={"verbose_name": "Měřidlo", "verbose_name_plural": "Měřidla", "ordering": ["site", "meter_type", "name"]},
        ),
        migrations.CreateModel(
            name="Period",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.PositiveIntegerField(verbose_name="Rok")),
                ("month", models.PositiveSmallIntegerField(verbose_name="Měsíc")),
                ("status", models.CharField(choices=[("open", "Otevřeno"), ("closed", "Uzavřeno")], default="open", max_length=10, verbose_name="Stav")),
            ],
            options={"verbose_name": "Období", "verbose_name_plural": "Období", "ordering": ["-year", "-month"], "unique_together": {("year", "month")}},
        ),
        migrations.CreateModel(
            name="MeterReading",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reading_date", models.DateField(verbose_name="Datum odečtu")),
                ("value", models.DecimalField(decimal_places=3, max_digits=14, verbose_name="Stav měřidla")),
                ("is_estimate", models.BooleanField(default=False, verbose_name="Odhad")),
                ("note", models.CharField(blank=True, max_length=300, verbose_name="Poznámka")),
                ("meter", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="readings", to="core.meter", verbose_name="Měřidlo")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="readings", to="core.period", verbose_name="Období")),
            ],
            options={"verbose_name": "Odečet měřidla", "verbose_name_plural": "Odečty měřidel", "ordering": ["-period", "meter"], "unique_together": {("meter", "period")}},
        ),
        migrations.CreateModel(
            name="ServicePoolItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Název")),
                ("invoice_class", models.CharField(choices=[("rent", "Nájemné"), ("electricity", "Elektřina"), ("water", "Voda"), ("heat", "Teplo"), ("other", "Ostatní")], default="other", max_length=20, verbose_name="Třída")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_items", to="core.site", verbose_name="Areál")),
                ("unit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="service_items", to="core.unit", verbose_name="Prostor")),
                ("meter", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="service_items", to="core.meter", verbose_name="Měřidlo")),
            ],
            options={"verbose_name": "Položka zásobníku", "verbose_name_plural": "Zásobník", "ordering": ["site", "invoice_class", "name"]},
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
                ("service_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocation_keys", to="core.servicepoolitem", verbose_name="Položka zásobníku")),
                ("meter", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="submeter_keys", to="core.meter", verbose_name="Podružné měřidlo")),
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
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="billing_lines", to="core.period", verbose_name="Období")),
                ("service_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="billing_lines", to="core.servicepoolitem", verbose_name="Položka zásobníku")),
            ],
            options={"verbose_name": "Vyúčtovaná položka", "verbose_name_plural": "Vyúčtované položky", "ordering": ["-period", "client_card", "service_item"], "unique_together": {("client_card", "period", "service_item")}},
        ),
    ]
