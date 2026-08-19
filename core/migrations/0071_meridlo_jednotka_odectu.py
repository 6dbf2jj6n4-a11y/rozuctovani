"""Jednotka odectu (na displeji meridla).

Na strance Zadavani odectu se u policka ukazovala `unit_of_measure`,
jenze to je jednotka az PO prepoctu koeficientem. U meridel tepla
s koeficientem 0,0036 (prevod kWh -> GJ) se tak zadavaly kWh, ale
u policka svitilo GJ. Viz konverzace s Danielem 2026-08-19.

Migrace doplni "kWh" u meridel, kde je prevod jednoznacny: koeficient
0,0036 je presne 1 kWh = 0,0036 GJ (help_text u pole `coefficient`
uvadi presne tenhle priklad). Meridla s koeficientem 1 se nechavaji
prazdna - tam se odecet cte primo v `unit_of_measure`, takze zadne
rozliseni netreba.

Rucne psana migrace - makemigrations v tomhle repu navrhuje i
nesouvisejici stare drifty (viz pamet projektu).
"""
from decimal import Decimal

from django.db import migrations, models

KOEFICIENT_KWH_NA_GJ = Decimal("0.0036")


def doplnit_kwh(apps, schema_editor):
    Meter = apps.get_model("core", "Meter")
    pocet = Meter.objects.filter(coefficient=KOEFICIENT_KWH_NA_GJ).update(
        reading_unit_of_measure="kWh"
    )
    print(f"  Jednotka odectu 'kWh' doplnena u {pocet} meridel (koeficient 0,0036 = kWh -> GJ)")


def zpet(apps, schema_editor):
    Meter = apps.get_model("core", "Meter")
    Meter.objects.update(reading_unit_of_measure="")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0070_prostor_bytovy_nebytovy"),
    ]

    operations = [
        migrations.AddField(
            model_name="meter",
            name="reading_unit_of_measure",
            field=models.CharField(
                "Jednotka odečtu (na displeji)",
                max_length=20,
                blank=True,
                default="",
                help_text=(
                    "Jednotka, ve které se odečet fyzicky čte z měřidla - zobrazí se "
                    "na stránce Zadávání odečtů. Vyplň jen když se liší od Měrné "
                    "jednotky, tedy když je Koeficient jiný než 1 (např. teplo se "
                    "čte v kWh, ale vykazuje v GJ). Prázdné = stejná jako Měrná jednotka."
                ),
            ),
        ),
        migrations.RunPython(doplnit_kwh, zpet),
    ]
