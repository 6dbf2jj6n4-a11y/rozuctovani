"""Pocet osob pro TUV se uz nedosazuje z Poctu osob - TUV klice berou jen
vlastni pole. Meni se jen napoveda. Viz Daniel 2026-09-25."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0110_pocet_osob_tuv"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clientcard",
            name="pocet_osob_tuv",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Počet osob pro TUV",
                help_text=(
                    "Kolik lidí používá teplou vodu. Klíče s váhou „Počet osob pro "
                    "TUV z karty“ berou JEN tohle pole (ne Počet osob) - u karty "
                    "s klíči na TUV musí být vyplněné, i když je číslo stejné."
                ),
            ),
        ),
    ]
