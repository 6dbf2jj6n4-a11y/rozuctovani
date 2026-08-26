"""Přejmenování typů rozpočtu - „Podle váhy na měřidle" / „bez měřidla".

„Podružné měřidlo (1:1)" svádělo k tomu, že měřidlo má klient sám pro
sebe. Když ho ale sdílí víc karet, engine dělí jeho spotřebu mezi ně
podle Hodnoty - tedy stejně jako „Podle váhy", jen se nejdřív z celku
vyřízne skutečná spotřeba toho měřidla. Nová dvojice názvů to říká přímo.

**Ukládaná hodnota se NEMĚNÍ** ("submeter" / "weighted_count"), jde
čistě o popisky a nápovědu - proto tu nejsou žádná data k převodu.

Psáno ručně, ne přes makemigrations: to na tomhle repu navrhuje i
nesouvisející změny z historického driftu mezi modely a migracemi.
Daniel 2026-08-26.
"""
from django.db import migrations, models

TYPY = [
    ("submeter", "Podle váhy na měřidle"),
    ("fixed_amount", "Pevná částka"),
    ("weighted_count", "Podle váhy bez měřidla"),
    ("area_price", "Dle výměry (m²)"),
]

NAPOVEDA_TYP = (
    "„Podle váhy na měřidle“ nejdřív vyřízne z položky skutečnou "
    "spotřebu zvoleného měřidla a teprve tu rozdělí – mezi karty, "
    "které měřidlo sdílejí, poměrem podle Hodnoty (m², osoby, kusy). "
    "Když je na měřidle karta sama, dostane celou jeho spotřebu. "
    "„Podle váhy bez měřidla“ dělí náklad položky rovnou podle "
    "Hodnoty, bez ohledu na to, kolik se kde skutečně naměřilo."
)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0087_planek_soubor_nepovinny"),
    ]

    operations = [
        migrations.AlterField(
            model_name="allocationkey",
            name="allocation_type",
            field=models.CharField(
                choices=TYPY, help_text=NAPOVEDA_TYP, max_length=20,
                verbose_name="Typ rozpočtu",
            ),
        ),
        migrations.AlterField(
            model_name="servicepoolitem",
            name="default_allocation_type",
            field=models.CharField(
                blank=True, choices=TYPY, max_length=20,
                help_text=(
                    "Předvyplní se při založení nového klíče na kartě "
                    "klienta pro tuto položku."
                ),
                verbose_name="Výchozí typ rozpočtu",
            ),
        ),
        # Tytéž volby používá i Výchozí služba u Plochy - bez toho by
        # makemigrations pořád hlásil nesoulad.
        migrations.AlterField(
            model_name="unitservice",
            name="allocation_type",
            field=models.CharField(
                choices=TYPY, default="submeter", max_length=20,
                verbose_name="Typ rozpočtu",
            ),
        ),
    ]
