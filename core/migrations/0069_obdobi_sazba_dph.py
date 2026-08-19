"""Sazba DPH jako pole Obdobi.

Drive to byla konstanta v core/admin.py (_SAZBA_DPH). Sazba je u
Obdobi, aby jeji budouci zmena neprepsala zpetne uz uzavrena obdobi -
stara vyuctovani musi zustat spocitana sazbou, ktera tehdy platila.
Vychozi 21 % odpovida zakladni sazbe overene proti ABRA Flexi
(sazbaDphZakl). Viz konverzace s Danielem 2026-08-19.

Rucne psana migrace - makemigrations v tomhle repu navrhuje i
nesouvisejici stare drifty (viz pamet projektu).
"""
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0068_nefakturovana_cast_na_plose"),
    ]

    operations = [
        migrations.AddField(
            model_name="period",
            name="vat_rate",
            field=models.DecimalField(
                "Sazba DPH (%)",
                max_digits=5,
                decimal_places=2,
                default=Decimal("21"),
                help_text=(
                    "Základní sazba DPH platná v tomto období - používá se ve sloupcích "
                    "„vč. DPH\" v Přehledu nájemného. Je u období, aby změna sazby "
                    "neovlivnila zpětně už uzavřená období."
                ),
            ),
        ),
    ]
