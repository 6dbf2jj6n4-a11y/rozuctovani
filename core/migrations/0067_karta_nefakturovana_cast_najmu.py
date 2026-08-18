"""Nefakturovana cast najmu na Karte klienta.

Nekteri klienti plati cast najmu bez dokladu (viz Ing. Roman Chamrad,
4 000 Kc/mesic) - do najmu a sestav to patri, ale nefakturuje se to a
nesmi to vstupovat do koeficientu DPH, protoze to neni zdanitelne
plneni. Viz konverzace s Danielem 2026-08-18.

Rucne psana migrace jen s timhle jednim polem - makemigrations v tomhle
repu navrhuje i nesouvisejici stare drifty mezi modely a historii
migraci (viz pamet projektu).
"""
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0066_trida_verbose_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientcard",
            name="rent_not_invoiced",
            field=models.DecimalField(
                "Nefakturovaná část nájmu (Kč/měsíc)",
                max_digits=10,
                decimal_places=2,
                default=Decimal("0"),
                help_text=(
                    "Část měsíčního nájmu, kterou klient platí bez dokladu - do nájmu "
                    "a sestav se počítá dál, ale NEfakturuje se a nevstupuje do "
                    "koeficientu DPH (není zdanitelné plnění). Nech 0, pokud se "
                    "fakturuje celý nájem."
                ),
            ),
        ),
    ]
