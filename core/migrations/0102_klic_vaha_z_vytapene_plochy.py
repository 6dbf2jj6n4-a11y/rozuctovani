"""Vaha klice dopoctena z vytapene plochy karty.

Prechod tepla NJ na m2 (viz preklicovat_teplo_nj_m2) zapsal do kazdeho
klice soucet vytapenych m2 jako pevnou Hodnotu. Hned se ukazalo, v cem
je to krehke: kdyz po ukonceni najmu Aktiv Novostav presly jeho plochy
na pronajimatele, vaha na karte CALAMARI zustala stara a musela se
prepocitat rucne prikazem. Daniel 2026-09-05: "musime zajistit, ze to
provede sam model a my to jenom schvalime."

Klic proto nove umi rict "vaha = vytapena plocha teto karty" a spocita
se az pri rozuctovani (AllocationKey.vaha). Zmena ploch se tim promitne
sama - pridani, ubrani i oprava vymery. V Karte klienta je klic dal
videt, jen misto cisla ukazuje "219 m2 vytapene plochy".

Data: zapnuto u vsech vazenych klicu polozky "hlavni odber teplo NJ"
a jejich Hodnota se vynuluje, aby nebylo pochyb, ktere cislo plati.
Pevna castka FSL CZ zustava nedotcena.
"""
from django.db import migrations, models

NAPOVEDA = (
    "Místo pevné Hodnoty se váha vezme jako součet vytápěných m² "
    "všech Ploch téhle Karty. Přepočítá se sama při každém "
    "rozúčtování, takže se nerozejde, když se plocha přidá, ubere "
    "nebo se opraví výměra - na rozdíl od čísla opsaného do "
    "Hodnoty. Používá se u tepla, kde se dělí podle velikosti "
    "vytápěného prostoru."
)


def zapnout(apps, schema_editor):
    apps.get_model("core", "AllocationKey").objects.filter(
        service_item__site__name="NJ",
        service_item__name="hlavní odběr teplo NJ",
        allocation_type="weighted_count",
    ).update(weight_from_heated_area=True, value=None)


def zpet(apps, schema_editor):
    """Priznak zanikne s polem; Hodnoty uz zpatky dopocitat nejde."""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0101_prostor_pocet_radiatoru"),
    ]

    operations = [
        migrations.AddField(
            model_name="allocationkey",
            name="weight_from_heated_area",
            field=models.BooleanField(
                default=False, help_text=NAPOVEDA,
                verbose_name="Váha = vytápěná plocha karty",
            ),
        ),
        migrations.RunPython(zapnout, zpet),
    ]
