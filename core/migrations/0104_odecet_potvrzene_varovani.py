"""Stopa po potvrzenem varovani u odectu.

Zadavani odectu hlida neverohodnou spotrebu a pri podezreni si vyzada
potvrzeni - je to zamerne varovani, ne zakaz (klimatizace v lete nebo
novy najemce muzou spotrebu legitimne vystrelit). Po potvrzeni ale
nezustala zadna stopa a odecet vypadal jako kazdy jiny.

Prave tudy prosel u E_C1Z v NJ stav 1605 misto 605: osm mesicu nulova
spotreba, pak 1000 kWh navic. Kontrola varovani ukazala ("Meridlo dosud
nikdy nic nespotrebovalo"), spravce ho potvrdil a chyba se nasla az
nahodou okem o pet dni pozdeji. Daniel 2026-09-09.

Pole se vyplnuje samo pri zapisu z obrazovky Odectu a pri oprave na
verohodnou hodnotu se smaze.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0103_zdroj_vahy_klice"),
    ]

    operations = [
        migrations.AddField(
            model_name="meterreading",
            name="confirmed_warning",
            field=models.CharField(
                blank=True, max_length=300, verbose_name="Potvrzené varování",
                help_text=(
                    "Když Zadávání odečtů hlásilo nevěrohodnou spotřebu a správce ji "
                    "přesto potvrdil, zůstane tu důvod, který systém ukázal. Slouží "
                    "ke kontrole po kole odečtů - potvrzené varování je přesně to, "
                    "co má admin projít. Vyplňuje se samo, ručně se nezadává; při "
                    "opravě hodnoty na věrohodnou se smaže."
                ),
            ),
        ),
    ]
