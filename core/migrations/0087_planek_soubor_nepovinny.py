"""Soubor u Plánku je nepovinný.

Výkres, ze kterého se doopravdy kreslí, sedí v `svg_text` (viz
Floorplan.read_svg). Plánky nahrané příkazem nahrat_planky mají jen ten -
soubory mají i desítky MB a nahrávat je ještě na R2 nemá smysl. Dokud
bylo pole povinné, formulář po nich chtěl soubor při KAŽDÉM uložení,
takže je nešlo ani přejmenovat. Že plánek nezůstane bez výkresu, hlídá
Floorplan.clean. Daniel 2026-08-25.

Psáno ručně, ne přes makemigrations - to na tomhle repu navrhuje i
nesouvisející změny z historického driftu mezi modely a migracemi.
"""
import core.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0086_psc_jednotny_tvar"),
    ]

    operations = [
        migrations.AlterField(
            model_name="floorplan",
            name="svg",
            field=models.FileField(
                blank=True,
                help_text=(
                    "Plain/Inkscape SVG s vrstvami „podklad“, „Plochy_rentex“ a "
                    "„Plochy_spolecne“. Každý tvar ve vrstvě Plochy_rentex musí mít "
                    "id shodné s názvem Pronajímaného prostoru (mezera → podtržítko). "
                    "Když už je výkres v databázi, soubor znovu nahrávat netřeba."
                ),
                storage=core.storage.R2MediaStorage(),
                upload_to="planky/",
                verbose_name="Výkres (SVG)",
            ),
        ),
    ]
