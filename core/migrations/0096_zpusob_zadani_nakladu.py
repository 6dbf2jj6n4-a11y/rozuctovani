"""Jasne rozdeleni, jak se u ktere polozky zadava Naklad za obdobi.

Dosud se u kazdeho Nakladu daly vyplnit obe pole - Fakturovane mnozstvi
i Castka - a nikde nebylo videt, ktere se ma vyplnit. U ostrahy nebo
uklidu nedava mnozstvi smysl vubec, u energii je naopak mnozstvi to
hlavni. Daniel 2026-09-04: "Sam uz nevim, jestli mam zadavat jednotky
i castku nebo jen jedno."

ServicePoolItem.cost_in_units to rika za polozku: zapnute u odberu, kde
dodavatel fakturuje mnozstvi (kWh, m3, GJ, kg), vypnute u sluzeb
fakturovanych rovnou castkou. Formular podle toho ukaze jen to pole,
ktere ma smysl, a Naklad s mnozstvim u castkove polozky se neulozi.

PriceList.is_estimate resi druhou vec: dopocet z Ceniku se dosud
oznacoval jako odhad vzdycky, coz je spatne. U vody se mnozstvi proste
vynasobi sjednanou cenou a nic odhadnuteho na tom neni - odhad je jen
tehdy, kdyz je predbezna sama cena v Ceniku (Daniel 2026-09-04).

Data:
  * cost_in_units zapnuto u odberu, ktere uz nekdy mnozstvi mely, plus
    u novych polozek DV (voda, teplo, elektrina) - u tech se meri taky,
    jen jeste nemaji zadny Naklad. Srazkove vody zustavaji castkove:
    jejich Cenik je cena za m2/rok pro klice "Dle vymery", ne prepocet
    fakturovaneho mnozstvi.
  * is_estimate zapnuto u tri cen zalozenych 2026-09-04 jako predbezne
    do prichodu faktur (elektrina FM a NJ, teplo FM za 08/2026).
"""
from django.db import migrations, models

# polozky, kde dodavatel fakturuje mnozstvi
V_JEDNOTKACH = [
    ("FM", "hlavní odběr elektro FM"),
    ("FM", "odběr EAN 668 FM"),
    ("FM", "hlavní odběr teplo FM"),
    ("FM", "hlavní odběr voda FM"),
    ("NJ", "hlavní odběr elektro NJ"),
    ("NJ", "hlavní odběr teplo NJ"),
    ("NJ", "hlavní odběr voda NJ"),
    ("DV", "hlavní odběr voda DV"),
    ("DV", "hlavní odběr teplo DV"),
    ("DV", "společná elektřina DV"),
    ("DV", "výtah DV"),
    ("DV", "odběr elektřiny nebytových prostor DV"),
]

# ceny zalozene jako predbezne do prichodu faktur
PREDBEZNE = [
    ("FM", "hlavní odběr elektro FM", 2026, 8),
    ("FM", "hlavní odběr teplo FM", 2026, 8),
    ("NJ", "hlavní odběr elektro NJ", 2026, 8),
]


def naplnit(apps, schema_editor):
    ServicePoolItem = apps.get_model("core", "ServicePoolItem")
    PriceList = apps.get_model("core", "PriceList")
    for areal, nazev in V_JEDNOTKACH:
        ServicePoolItem.objects.filter(site__name=areal, name=nazev).update(cost_in_units=True)
    for areal, nazev, rok, mesic in PREDBEZNE:
        PriceList.objects.filter(
            service_item__site__name=areal, service_item__name=nazev,
            period__year=rok, period__month=mesic,
        ).update(is_estimate=True)


def zpet(apps, schema_editor):
    """Priznaky se jen vynuluji - pole samotna rusi AddField."""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0095_naklad_odberneho_mista"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicepoolitem",
            name="cost_in_units",
            field=models.BooleanField(
                default=False, verbose_name="Náklad se zadává v jednotkách",
                help_text=(
                    "Zapni u odběrů, kde dodavatel fakturuje MNOŽSTVÍ (kWh, m³, GJ, "
                    "kg) - do Nákladu za období se pak zadává množství a Kč se "
                    "dopočítají cenou z Ceníku, nebo se zadá i částka z faktury. "
                    "Vypnuté je u služeb, které se fakturují jen částkou (ostraha, "
                    "úklid, revize, srážkové vody) - tam pole Fakturované množství "
                    "nedává smysl a nejde vyplnit."
                ),
            ),
        ),
        migrations.AddField(
            model_name="pricelist",
            name="is_estimate",
            field=models.BooleanField(
                default=False, verbose_name="Předběžná cena",
                help_text=(
                    "Zaškrtni, když cena není sjednaná ani z faktury, ale jen odhad "
                    "do doby, než faktura přijde. Částky z ní dopočítané se v "
                    "Nákladech za období označí jako odhad. U cen platných celý rok "
                    "(vodné/stočné, pelety) nech vypnuté - tam je dopočet z Ceníku "
                    "normální způsob zadání, ne odhad."
                ),
            ),
        ),
        migrations.RunPython(naplnit, zpet),
    ]
