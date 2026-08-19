"""Merna jednotka se predvyplnuje podle Tridy + srovnani "m2" na "m²".

1. Pole `Meter.unit_of_measure` melo natvrdo default="kWh", takze
   vodomer i teplomer zalozeny bez vyplneni jednotky dostal kWh - presne
   tak vznikl W_FM_CELKEM s kWh misto m³ (opraveno migraci 0072). Ted je
   pole prazdne a doplni se ve `Meter.save()` podle vychozi jednotky
   Tridy.
2. UKLID_FM melo jednotku "m2", zatimco jinde v aplikaci se plocha pise
   "m²" - srovnano.

Existujici meridla maji jednotku vyplnenou, zmena defaultu se jich
netyka. Viz konverzace s Danielem 2026-08-19.

Rucne psana migrace - makemigrations v tomhle repu navrhuje i
nesouvisejici stare drifty (viz pamet projektu).
"""
from django.db import migrations, models


def srovnat_m2(apps, schema_editor):
    Meter = apps.get_model("core", "Meter")
    pocet = Meter.objects.filter(unit_of_measure="m2").update(unit_of_measure="m²")
    print(f"  Jednotka 'm2' srovnana na 'm²': {pocet} meridel")


def zpet_m2(apps, schema_editor):
    Meter = apps.get_model("core", "Meter")
    Meter.objects.filter(unit_of_measure="m²").update(unit_of_measure="m2")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0072_srovnat_jednotky_vody"),
    ]

    operations = [
        migrations.AlterField(
            model_name="meter",
            name="unit_of_measure",
            field=models.CharField(
                "Měrná jednotka",
                max_length=20,
                blank=True,
                default="",
                help_text=(
                    "Nech prázdné a doplní se výchozí jednotka Třídy (Nastavení → Třídy). "
                    "Dřív tu byla natvrdo „kWh“, takže vodoměr nebo teploměr založený bez "
                    "vyplnění jednotky dostal kWh."
                ),
            ),
        ),
        migrations.RunPython(srovnat_m2, zpet_m2),
    ]
