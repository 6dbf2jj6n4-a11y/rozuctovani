"""Priznak Bytovy/Nebytovy prostor u Pronajimanych prostor.

Vsechny prostory se nastavi jako NEBYTOVE (default), krome arealu DV -
tam jsou podle Daniela vsechny prostory bytove (viz konverzace
2026-08-19). Areal se hleda podle nazvu 'DV'; kdyby v DB nebyl,
migrace jen nic nenastavi a nespadne.

Rucne psana migrace - makemigrations v tomhle repu navrhuje i
nesouvisejici stare drifty (viz pamet projektu).
"""
from django.db import migrations, models

AREAL_S_BYTY = "DV"


def oznacit_byty(apps, schema_editor):
    Unit = apps.get_model("core", "Unit")
    pocet = Unit.objects.filter(site__name=AREAL_S_BYTY).update(is_residential=True)
    print(f"  Nastaveno jako bytovy prostor: {pocet} prostor v arealu {AREAL_S_BYTY}")


def zrusit_byty(apps, schema_editor):
    Unit = apps.get_model("core", "Unit")
    Unit.objects.filter(site__name=AREAL_S_BYTY).update(is_residential=False)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0069_obdobi_sazba_dph"),
    ]

    operations = [
        migrations.AddField(
            model_name="unit",
            name="is_residential",
            field=models.BooleanField(
                "Bytový prostor",
                default=False,
                help_text=(
                    "Zapnuto = bytový prostor, vypnuto = nebytový. Nájem bytu je "
                    "podle §56a vždy osvobozený od DPH a nelze ho zdanit ani "
                    "nájemci, který je plátce - na rozdíl od nebytových prostor."
                ),
            ),
        ),
        migrations.RunPython(oznacit_byty, zrusit_byty),
    ]
