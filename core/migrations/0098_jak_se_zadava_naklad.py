"""Tri zpusoby zadani Nakladu misto dvou.

Priznak z migrace 0096 rozlisoval jen "v jednotkach" / "castkou". Nestacilo
to: u vodneho a stocneho je cena sjednana na cely rok, takze se ma zadavat
POUZE mnozstvi a Kc se dopoctou z Ceniku - castka se u nej zadavat nema
vubec, aby nesla omylem prebit sjednanou cenu (Daniel 2026-09-05).

Zpusoby:
  * "castka"   - sluzby fakturovane rovnou castkou (ostraha, uklid,
                 revize, srazkove vody); zamkne se Mnozstvi
  * "mnozstvi" - odbery se sjednanou cenou (vodne/stocne, pelety);
                 zamkne se Castka
  * "oboji"    - odbery, kde faktura uvadi obojí a cena se meni po
                 mesicich (elektrina, teplo); nezamyka se nic

Rozdeleni podle skutecnosti v datech: polozky, ktere maji nekdy zadane
mnozstvi I castku, dostaly "oboji"; vodne/stocne a pelety "mnozstvi";
zbytek "castka". Polozky DV zatim zadny Naklad nemaji - voda a teplo se
resi jako jinde, elektrina dostala "oboji", coz nic nezamyka.
"""
from django.db import migrations, models

MNOZSTVI = [
    ("FM", "hlavní odběr voda FM"),
    ("NJ", "hlavní odběr voda NJ"),
    ("NJ", "hlavní odběr teplo NJ"),
    ("DV", "hlavní odběr voda DV"),
    ("DV", "hlavní odběr teplo DV"),
]

OBOJI = [
    ("FM", "hlavní odběr elektro FM"),
    ("FM", "odběr EAN 668 FM"),
    ("FM", "hlavní odběr teplo FM"),
    ("NJ", "hlavní odběr elektro NJ"),
    ("DV", "společná elektřina DV"),
    ("DV", "výtah DV"),
    ("DV", "odběr elektřiny nebytových prostor DV"),
]

VOLBY = [
    ("castka", "Jen částku (Kč)"),
    ("mnozstvi", "Jen množství – Kč se dopočítá z Ceníku"),
    ("oboji", "Množství i částku z faktury"),
]

NAPOVEDA = (
    "Řídí, která pole jde u Nákladu za období vyplnit - ostatní se "
    "zamknou.\n"
    "• Jen částku: služby fakturované rovnou částkou (ostraha, úklid, "
    "revize, srážkové vody).\n"
    "• Jen množství: odběry se sjednanou cenou platnou celé období "
    "(vodné/stočné, pelety) - zadá se jen množství a Kč se dopočítají "
    "z Ceníku.\n"
    "• Množství i částku: odběry, kde faktura uvádí obojí a cena se "
    "mění po měsících (elektřina, teplo)."
)


def naplnit(apps, schema_editor):
    ServicePoolItem = apps.get_model("core", "ServicePoolItem")
    for zpusob, seznam in (("mnozstvi", MNOZSTVI), ("oboji", OBOJI)):
        for areal, nazev in seznam:
            ServicePoolItem.objects.filter(
                site__name=areal, name=nazev).update(cost_input=zpusob)


def zpet(apps, schema_editor):
    """Zpatky na dvouhodnotovy priznak - "castka" byla vypnuta, zbytek zapnuty."""
    ServicePoolItem = apps.get_model("core", "ServicePoolItem")
    ServicePoolItem.objects.exclude(cost_input="castka").update(cost_in_units=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0097_napovedy_zadani_nakladu"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicepoolitem",
            name="cost_input",
            field=models.CharField(
                choices=VOLBY, default="castka", help_text=NAPOVEDA,
                max_length=20, verbose_name="Jak se zadává náklad",
            ),
        ),
        migrations.RunPython(naplnit, zpet),
        migrations.RemoveField(model_name="servicepoolitem", name="cost_in_units"),
    ]
