"""Treti volba u Typu osoby: Nepodnikatelsky subjekt.

Soukroma osoba, ale i SVJ nebo spolek - z cele sekce Identifikace se
takoveho klienta tyka jen IČO (SVJ a spolky ho maji) a insolvence
(osobni bankrot). Ostatni pole se v adminu skryvaji a pri ulozeni
vyprazdnuji, viz Client.save a ClientAdmin.conditional_fields.

Na Danielovo prani 2026-08-19. Jen rozsireni choices - na data ani
schema to nema vliv, zadny existujici klient se nemeni.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0079_cardunit_monthly_rent_override"),
    ]

    operations = [
        migrations.AlterField(
            model_name="client",
            name="entity_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("pravnicka", "Právnická osoba"),
                    ("fyzicka", "Fyzická osoba"),
                    ("nepodnikatel", "Nepodnikatelský subjekt"),
                ],
                max_length=20,
                verbose_name="Typ osoby",
            ),
        ),
    ]
