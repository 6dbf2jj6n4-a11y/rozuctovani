"""Kod meridla musi byt jedinecny v ramci arealu.

Daniel narazil na to, ze v naseptavaci Podruzneho meridla u Klice byly
dve polozky "E_SPOL" (jedna FM, jedna NJ) a neslo poznat, kterou vybrat.
Popisek uz areal ukazuje (MeterAdmin.serialize_result); tahle migrace
resi tu druhou, skrytou cast problemu.

Kod ZAMERNE neni jedinecny globalne - stejny kod ve dvou arealech je
v poradku (takovych je 10: E_A1, E_B1, E_B2, E_D1, E_D2, E_D3, E_SPOL,
T_SPOLECNA, T_TUV, W_TUV) a vzorce si meridlo hledaji vzdy v ramci sveho
arealu. Ale DVA STEJNE KODY V JEDNOM AREALU by vzorce rozbily TISE -
`_formula_consumption_for` bere `.first()`, takze by pocital s nahodnym
z nich. Dosud tomu nebranilo nic; v datech zadna takova duplicita neni
(overeno 2026-08-20), takze migrace jen zavira diru do budoucna.

Prazdny kod je z omezeni vynechan - je to volitelne pole (dnes ho ma
vyplneny vsech 145 meridel).

Rucne psana migrace - makemigrations v tomhle repu navrhuje i
nesouvisejici stare drifty (viz pamet projektu).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0075_sjednotit_telefony"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="meter",
            constraint=models.UniqueConstraint(
                fields=["site", "code"],
                condition=~models.Q(code=""),
                name="meridlo_kod_jedinecny_v_arealu",
                violation_error_message=(
                    "Měřidlo s tímto kódem už v tomto areálu existuje. "
                    "Kód musí být v rámci areálu jedinečný, jinak by vzorce "
                    "virtuálních měřidel nevěděly, které z nich použít."
                ),
            ),
        ),
    ]
