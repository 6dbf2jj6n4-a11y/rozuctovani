"""Pocet radiatoru na Prostoru.

Teplo v NJ se prepina na vytapenou plochu, cimz by se pocty radiatoru
(dosud ulozene jako vahy klicu na T_INDIVIDUALNI) ztratily. Daniel
2026-09-05: "mozna bych u tech predmetu najmu nechal i pole pocet
radiatoru - pokud bychom se chteli vratit k rozpoctu podle radiatoru,
staci zmenit, co je vahou."

Radiatory se dosud vedly po KLIENTECH, ne po prostorech, takze rozpad
na jednotlive prostory z dat odvodit nejde. Predvyplni se proto jen
tam, kde je jednoznacny - klient s jedinym vytapenym prostorem. Zbytek
zustava prazdny a doplni se rucne.

Predvyplnene (klient -> prostor = pocet):
  Delphia MORAVIA   AB 2.10 = 1     MastrCrane      AB 2.09 = 1
  KJO EU            AB 3.14 = 1     Michal Gnes     AB 2.04 = 1
  Maker Inspiration AB 2.05 = 2     MV Active       AB 1.23 = 4

Nerozpadle (klient: radiatoru celkem, vytapenych prostoru):
  Aktiv Novostav 2/5, BURNING 3/3, CALAMARI 3/4, INNEXUM 2/2,
  MI Roads 6/6, ONE KLIMA 3/2, TSC Cleaning 1/2
"""
from django.db import migrations, models

JEDNOZNACNE = {
    "AB 2.10": 1,
    "AB 3.14": 1,
    "AB 2.05": 2,
    "AB 2.09": 1,
    "AB 2.04": 1,
    "AB 1.23": 4,
}


def predvyplnit(apps, schema_editor):
    Unit = apps.get_model("core", "Unit")
    for nazev, pocet in JEDNOZNACNE.items():
        Unit.objects.filter(site__name="NJ", name=nazev).update(radiator_count=pocet)


def zpet(apps, schema_editor):
    """Hodnoty zaniknou s polem."""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0100_prostor_vytapeni"),
    ]

    operations = [
        migrations.AddField(
            model_name="unit",
            name="radiator_count",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Počet radiátorů",
                help_text=(
                    "Kolik je v prostoru radiátorů. Teplo se dnes rozúčtovává podle "
                    "vytápěné plochy, ale kdyby se mělo vrátit k radiátorům, stačí "
                    "přepsat váhu na klíčích - údaj tím zůstává po ruce. Jen "
                    "informativní, sám na výpočet nemá vliv."
                ),
            ),
        ),
        migrations.RunPython(predvyplnit, zpet),
    ]
