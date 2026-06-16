import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

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
    ]
