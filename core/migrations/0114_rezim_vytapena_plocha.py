"""Meridlo muze misto odectu secist vytapenou plochu Prostoru arealu -
spolecnych, nebo ostatnich. Pseudomeridla T_SPOLECNA a T_INDIVIDUALNI
tak deli teplo NJ na spolecnou a individualni cast v pomeru m2 bez
rucnich odectu (Daniel 2026-09-27)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0113_pausal_za_tridu"),
    ]

    operations = [
        migrations.AlterField(
            model_name="meter",
            name="reading_mode",
            field=models.CharField(
                choices=[
                    ("state", "Stavy (kumulativní odečet, spotřeba = rozdíl mezi obdobími)"),
                    ("consumption", "Spotřeba za období (dodavatel hlásí rovnou spotřebu, ne stav)"),
                    ("vyt_spolecna", "Vytápěná plocha společných prostor (m², počítá se sama)"),
                    ("vyt_ostatni", "Vytápěná plocha ostatních prostor (m², počítá se sama)"),
                ],
                default="state",
                help_text=(
                    "Většina měřidel hlásí kumulativní Stav (spotřeba se dopočítá jako "
                    "rozdíl vůči minulému období). Pokud dodavatel hlásí rovnou Spotřebu "
                    "za období (např. hlavní odběrné místo elektro), přepni na tento režim "
                    "- pak stačí zadat odečet jen za aktuální období, hodnota se použije přímo."
                ),
                max_length=20,
                verbose_name="Způsob zadávání odečtů",
            ),
        ),
    ]
