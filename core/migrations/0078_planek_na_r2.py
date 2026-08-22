"""Vykres Planku uklada na Cloudflare R2, stejne jako foto odectu.

Puvodne mirilo pole na lokalni MEDIA_ROOT, protoze jsem se mylne domníval,
ze trvale uloziste neni - kontejner opravdu zadny disk nema, ale aplikace uz
R2 pouziva (core/storage.py). `svg_text` v databazi zustava jako zdroj pro
vykreslovani, viz komentar u pole.

Rucne psana, zamerne uzka migrace (viz 0077).
"""
import core.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0077_planek"),
    ]

    operations = [
        migrations.AlterField(
            model_name="floorplan",
            name="svg",
            field=models.FileField(
                help_text=(
                    "Plain/Inkscape SVG s vrstvami „podklad“, „Plochy_rentex“ a "
                    "„Plochy_spolecne“. Každý tvar ve vrstvě Plochy_rentex musí mít "
                    "id shodné s názvem Pronajímaného prostoru (mezera → podtržítko)."
                ),
                storage=core.storage.R2MediaStorage(),
                upload_to="planky/",
                verbose_name="Výkres (SVG)",
            ),
        ),
        migrations.AlterField(
            model_name="floorplan",
            name="svg_text",
            field=models.TextField(
                blank=True,
                editable=False,
                help_text=(
                    "Text nahraneho SVG. Puvodni soubor lezi na R2 (stejne jako foto "
                    "odectu), tohle je jeho kopie v databazi pro vykreslovani: planek "
                    "se cte pri KAZDEM zobrazeni stranky a jeden dotaz do Postgresu je "
                    "rychlejsi a spolehlivejsi nez HTTP dotaz do objektoveho ulozistě."
                ),
                verbose_name="Obsah výkresu",
            ),
        ),
    ]
