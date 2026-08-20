"""Priznak, zda areal vstupuje do koeficientu DPH.

Koeficient se pocita za jednu osobu (plátce DPH). Danielova firma
pronajima FM a NJ, kdezto areal DV je veden na fyzickou osobu, takze
do koeficientu firmy nepatri. Viz konverzace s Danielem 2026-08-19.

Priznak slouzi jako VYCHOZI zaskrtnuti v Prehledu najemneho - vyber
arealu jde v sestave kdykoli zmenit.

Rucne psana migrace - makemigrations v tomhle repu navrhuje i
nesouvisejici stare drifty (viz pamet projektu).
"""
from django.db import migrations, models

MIMO_KOEFICIENT = ["DV"]


def vyradit_dv(apps, schema_editor):
    Site = apps.get_model("core", "Site")
    pocet = Site.objects.filter(name__in=MIMO_KOEFICIENT).update(in_vat_coefficient=False)
    print(f"  Mimo koeficient DPH nastaveno: {pocet} arealu ({', '.join(MIMO_KOEFICIENT)})")


def zpet(apps, schema_editor):
    Site = apps.get_model("core", "Site")
    Site.objects.filter(name__in=MIMO_KOEFICIENT).update(in_vat_coefficient=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0073_jednotka_podle_tridy"),
    ]

    operations = [
        migrations.AddField(
            model_name="site",
            name="in_vat_coefficient",
            field=models.BooleanField(
                "Vstupuje do koeficientu DPH",
                default=True,
                help_text=(
                    "Zapnuto: nájem z tohoto areálu se počítá do koeficientu DPH "
                    "v Přehledu nájemného. Vypni u areálu, který pronajímá jiná osoba "
                    "než plátce, za kterého se koeficient počítá - třeba areál vedený "
                    "na fyzickou osobu. Slouží jen jako výchozí zaškrtnutí, v sestavě "
                    "jde výběr areálů kdykoli změnit."
                ),
            ),
        ),
        migrations.RunPython(vyradit_dv, zpet),
    ]
