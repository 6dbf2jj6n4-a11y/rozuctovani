"""Spolubydlici u Karty klienta.

Byt v arealu DV casto uziva vic lidi a kdyz nejsou manzele, maji ruzna
prijmeni. Platcem zustava jeden klient (najemce), ostatni se zapisuji
jako osoby u Karty - viz docstring modelu CardOccupant. Na Danielovo
prani 2026-08-19.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0080_nepodnikatelsky_subjekt"),
    ]

    operations = [
        migrations.CreateModel(
            name="CardOccupant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Jméno")),
                ("note", models.CharField(
                    blank=True,
                    help_text="Např. vztah k nájemci nebo od kdy v bytě bydlí.",
                    max_length=200, verbose_name="Poznámka",
                )),
                ("card", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="occupants", to="core.clientcard",
                    verbose_name="Karta klienta",
                )),
            ],
            options={
                "verbose_name": "Spolubydlící",
                "verbose_name_plural": "Spolubydlící",
                "ordering": ["name"],
            },
        ),
    ]
