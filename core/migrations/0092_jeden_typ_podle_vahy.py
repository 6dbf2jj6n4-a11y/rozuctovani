"""Typy rozpoctu "na meridle" a "bez meridla" splynuly v jeden "Podle vahy".

Vypocet mezi nimi nikdy nerozlisoval: billing/engine.py se diva na to,
jestli je na Klici vyplnene Meridlo, a podle toho vaha deli bud spotrebu
toho meridla, nebo zbytek polozky zasobniku. Dva typy pro jednu vec jen
matly a daly se nastavit proti skutecnosti - v produkci bylo 78 Klicu na
FM a 35 v NJ oznacenych "bez meridla", pritom meridlo mely.

Nove tedy: "Podle vahy" + vyplnene Meridlo = vaha na spotrebe meridla,
"Podle vahy" bez Meridla = vaha na polozce zasobniku.

Data: vsechny zaznamy s "submeter" se prepisou na "weighted_count".
Vypocet se tim nemeni - overeno prepoctem 07/2026 na FM, kde vysel
nulovy rozdil.

Viz Daniel 2026-09-01.
"""
from django.db import migrations, models


def submeter_na_vahu(apps, schema_editor):
    for model, pole in (("AllocationKey", "allocation_type"),
                        ("ServicePoolItem", "default_allocation_type"),
                        ("UnitService", "allocation_type")):
        apps.get_model("core", model).objects.filter(
            **{pole: "submeter"}
        ).update(**{pole: "weighted_count"})


def zpet(apps, schema_editor):
    """Zpetny prevod neexistuje - puvodni rozliseni uz v datech neni."""


VOLBY = [
    ("weighted_count", "Podle váhy"),
    ("fixed_amount", "Pevná částka"),
    ("area_price", "Dle výměry (m²)"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0091_odecet_zadal"),
    ]

    operations = [
        migrations.RunPython(submeter_na_vahu, zpet),
        migrations.AlterField(
            model_name="allocationkey",
            name="allocation_type",
            field=models.CharField(choices=VOLBY, max_length=20, verbose_name="Typ rozpočtu"),
        ),
        migrations.AlterField(
            model_name="servicepoolitem",
            name="default_allocation_type",
            field=models.CharField(
                choices=VOLBY, default="weighted_count", max_length=20,
                verbose_name="Výchozí typ rozpočtu",
            ),
        ),
        migrations.AlterField(
            model_name="unitservice",
            name="allocation_type",
            field=models.CharField(
                choices=VOLBY, default="weighted_count", max_length=20,
                verbose_name="Typ rozpočtu",
            ),
        ),
    ]
