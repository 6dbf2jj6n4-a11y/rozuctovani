"""Popisky po slouceni typu "Podle vahy" + srovnani driftu z 0092.

Po migraci 0092 zustaly v adminu popisky, ktere mluvi o typech, jez uz
neexistuji - "Co je vahou (u klicu 'Podle vahy na meridle')" a napoveda
u Typu rozpoctu popisujici dva typy. Nove rikaji to, co plati: o zpusobu
deleni rozhoduje Meridlo na Klici, ne typ.

Zaroven se srovnava stav dvou poli, ktera 0092 zapsala jinak, nez je ma
model: ServicePoolItem.default_allocation_type ma byt blank=True bez
vychozi hodnoty (prazdne znamena "nepredvyplnovat") a UnitService
.allocation_type nema blank. Do dat to nesahalo, jen by pri kazdem
dalsim makemigrations vyskakovala tahle zmena jako nesouvisejici drift.

Viz Daniel 2026-09-04.
"""
from django.db import migrations, models

import core.models

VOLBY = [
    ("weighted_count", "Podle váhy"),
    ("fixed_amount", "Pevná částka"),
    ("area_price", "Dle výměry (m²)"),
]

NAPOVEDA_TYP = (
    "O způsobu dělení u „Podle váhy“ rozhoduje Měřidlo níže, ne typ. "
    "S vyplněným Měřidlem se z položky nejdřív vyřízne skutečná "
    "spotřeba toho měřidla a teprve ta se rozdělí – mezi karty, "
    "které měřidlo sdílejí, poměrem podle Hodnoty (m², osoby, kusy). "
    "Když je na měřidle karta sama, dostane celou jeho spotřebu. "
    "Bez Měřidla se náklad položky dělí rovnou podle Hodnoty, bez "
    "ohledu na to, kolik se kde skutečně naměřilo."
)

NAPOVEDA_HODNOTA = (
    "Význam závisí na typu: u 'Pevná částka' jde o hotovou Kč částku/měsíc, "
    "u 'Dle výměry (m2)' jde o výměru v m2 (cena/m2/rok se bere z Ceníku "
    "položky pro dané období), u „Podle váhy“ S MĚŘIDLEM se použije jen pokud "
    "stejné měřidlo sdílí více karet - pak jde o váhu pro rozdělení jeho "
    "spotřeby mezi ně (u jedné karty na měřidlo se nepoužije, dostane celou "
    "spotřebu). U „Podle váhy“ BEZ MĚŘIDLA jde o libovolné relativní číslo vyjadřující "
    "podíl na společném nákladu (m2, počet osob, počet kusů, radiátorů "
    "apod. - jednotka záleží na tom, jak položka danou spotřebu/náklad "
    "rozpočítává) - systém ho vždy normalizuje tak, aby součet všech karet "
    "dal dohromady 100 %, stačí tedy zadat správný POMĚR mezi kartami."
)

NAPOVEDA_VAHA_MERIDLO = (
    "Krátký popis, co hodnota Klíče typu 'Podle váhy' napojeného na "
    "toto měřidlo znamená - např. 'm2', 'počet osob', 'počet "
    "radiátorů'. Typické pro virtuální 'zbytková' měřidla jako "
    "E_SPOL, kde se jejich spotřeba dělí mezi více karet vahou. Jen "
    "informativní (zobrazuje se v adminu a v Kartě klienta), na "
    "samotný výpočet nemá vliv."
)

NAPOVEDA_VAHA_POLOZKA = (
    "Krátký popis, co hodnota Klíče typu 'Podle váhy' na téhle "
    "položce znamená - např. 'm2', 'počet osob'. Použije se jen "
    "u klíčů BEZ vlastního napojeného měřidla (ty mají přednost "
    "Meter.weight_unit_label - jedna položka může mít víc "
    "různých vážených skupin s různým významem váhy, např. "
    "'hlavní odběr elektro FM'). Jen informativní, na samotný "
    "výpočet nemá vliv."
)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0093_uzavreni_odectu"),
    ]

    operations = [
        migrations.AlterField(
            model_name="allocationkey",
            name="allocation_type",
            field=models.CharField(
                choices=VOLBY, help_text=NAPOVEDA_TYP, max_length=20,
                verbose_name="Typ rozpočtu",
            ),
        ),
        migrations.AlterField(
            model_name="allocationkey",
            name="value",
            field=models.DecimalField(
                blank=True, decimal_places=4, help_text=NAPOVEDA_HODNOTA,
                max_digits=12, null=True, verbose_name="Hodnota",
            ),
        ),
        migrations.AlterField(
            model_name="meter",
            name="weight_unit_label",
            field=models.CharField(
                blank=True, help_text=NAPOVEDA_VAHA_MERIDLO, max_length=100,
                verbose_name="Co je váhou (u klíčů s tímto měřidlem)",
            ),
        ),
        migrations.AlterField(
            model_name="servicepoolitem",
            name="weight_unit_label",
            field=models.CharField(
                blank=True, help_text=NAPOVEDA_VAHA_POLOZKA, max_length=100,
                verbose_name="Co je váhou (u klíčů bez měřidla)",
            ),
        ),
        # srovnani driftu z 0092 - do dat nesaha
        migrations.AlterField(
            model_name="servicepoolitem",
            name="default_allocation_type",
            field=models.CharField(
                blank=True, choices=VOLBY,
                help_text="Předvyplní se při založení nového klíče na kartě klienta pro tuto položku.",
                max_length=20, verbose_name="Výchozí typ rozpočtu",
            ),
        ),
        migrations.AlterField(
            model_name="unitservice",
            name="allocation_type",
            field=models.CharField(
                choices=VOLBY, default=core.models.AllocationKey.AllocationType["WEIGHTED_COUNT"],
                max_length=20, verbose_name="Typ rozpočtu",
            ),
        ),
    ]
