"""Spolecna plocha - satny, sprchy, chodby, kotelna.

Model dosud rozlisoval jen "na Karte" a "bez Karty", takze spolecne
zazemi nemelo kam patrit. Minuly tyden proto satny AB 1.17 a AB 1.18
v NJ skoncily na karte pronajimatele - jenze jejich naklad ma nest
vsichni najemci, ne pronajimatel. Daniel 2026-09-16.

Spolecna plocha na zadne Karte byt nema: tim, ze se nezapocita do
zadne vahy, se jeji dil nakladu rozpusti mezi ostatni pomerem jejich
ploch. Sestava "Plochy bez karty" ji proto preskakuje.

Data: zapnuto u AB 1.17 (satna) a AB 1.18 (sprchy) v NJ a zaroven se
odpojuji z karty pronajimatele.
"""
from django.db import migrations, models

NAPOVEDA = (
    "Prostor, který užívají všichni - šatny, sprchy, chodby, kotelna. "
    "Nepronajímá se, takže nepatří na žádnou Kartu: jeho náklad se "
    "rozpustí mezi nájemce poměrem jejich ploch, protože se do vah "
    "nezapočítá. V sestavě „Plochy bez karty“ se proto nehlásí jako "
    "chybějící."
)


def oznacit(apps, schema_editor):
    Unit = apps.get_model("core", "Unit")
    CardUnit = apps.get_model("core", "CardUnit")
    spolecne = Unit.objects.filter(site__name="NJ", name__in=("AB 1.17", "AB 1.18"))
    spolecne.update(is_common=True)
    CardUnit.objects.filter(unit__in=spolecne).delete()


def zpet(apps, schema_editor):
    """Priznak zanikne s polem; odpojeni z karty uz zpatky nejde."""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0105_nastaveni_rozuctovani"),
    ]

    operations = [
        migrations.AddField(
            model_name="unit",
            name="is_common",
            field=models.BooleanField(
                default=False, help_text=NAPOVEDA, verbose_name="Společná plocha"),
        ),
        migrations.RunPython(oznacit, zpet),
    ]
