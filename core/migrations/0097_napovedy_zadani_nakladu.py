"""Napovedy u Nakladu za obdobi po rozdeleni zpusobu zadani.

Puvodni zneni ("Pro merene sluzby / Pro nemerene sluzby") nikde nerikalo,
podle ceho se pozna, ktera polozka je ktera - Daniel 2026-09-04: "Sam uz
nevim, jestli mam zadavat jednotky i castku nebo jen jedno." Ted se
odkazuji na priznak cost_in_units z migrace 0096.

Zaroven se v napovede u Castky rika, ze NULA je platna odpoved. Drive ji
validace zakazovala, takze sezonni sluzby (odklizeni snehu, revize)
musely zustavat prazdne a hlasily se kazdy mesic jako nezadane, i kdyz
za dane obdobi opravdu nic nestaly.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0096_zpusob_zadani_nakladu"),
    ]

    operations = [
        migrations.AlterField(
            model_name="costentry",
            name="amount_units",
            field=models.DecimalField(
                blank=True, decimal_places=3, max_digits=14, null=True,
                verbose_name="Fakturované množství (jednotky)",
                help_text=(
                    "Množství z faktury dodavatele (kWh, m³, GJ, kg). Jen u položek, "
                    "které mají v Zásobníku služeb zapnuté „Náklad se zadává "
                    "v jednotkách“ - u ostatních se nevyplňuje."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="costentry",
            name="amount_czk",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=14, null=True,
                verbose_name="Částka (Kč)",
                help_text=(
                    "Fakturovaná částka. U položek zadávaných v jednotkách ji vyplň, "
                    "jen když ji faktura uvádí - jinak nech prázdné a Kč se dopočítají "
                    "z Ceníku. Nula je platná odpověď (za tohle období nic nestálo), "
                    "prázdné pole znamená „ještě nevím“ a položka se nerozúčtuje."
                ),
            ),
        ),
    ]
