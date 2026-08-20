"""Planky (2D pudorysy) - viz core/floorplan.py.

Rucne psana, zamerne uzka migrace: `makemigrations` v tomhle repu navrhuje
i nesouvisejici drift mezi modely a historii migraci (viz 0034/0037).
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0076_kod_meridla_jedinecny_v_arealu"),
    ]

    operations = [
        migrations.CreateModel(
            name="Floorplan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Např. „Administrativní budova – 2.NP“.", max_length=200, verbose_name="Název")),
                (
                    "svg",
                    models.FileField(
                        help_text=(
                            "Plain/Inkscape SVG s vrstvami „podklad“, „Plochy_rentex“ a "
                            "„Plochy_spolecne“. Každý tvar ve vrstvě Plochy_rentex musí mít "
                            "id shodné s názvem Pronajímaného prostoru (mezera → podtržítko)."
                        ),
                        upload_to="planky/",
                        verbose_name="Výkres (SVG)",
                    ),
                ),
                (
                    "svg_text",
                    models.TextField(
                        blank=True,
                        editable=False,
                        help_text=(
                            "Text nahraneho SVG. Drzi se v databazi zamerne: kontejner na "
                            "Railway nema trvaly disk (jediny volume patri Postgresu), takze "
                            "nahrany soubor by pri kazdem nasazeni zmizel."
                        ),
                        verbose_name="Obsah výkresu",
                    ),
                ),
                ("order", models.IntegerField(default=0, help_text="Menší číslo je výš. Typicky podle podlaží.", verbose_name="Pořadí")),
                ("is_active", models.BooleanField(default=True, verbose_name="Aktivní")),
                ("note", models.CharField(blank=True, max_length=300, verbose_name="Poznámka")),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="floorplans",
                        to="core.site",
                        verbose_name="Areál",
                    ),
                ),
            ],
            options={
                "verbose_name": "Plánek",
                "verbose_name_plural": "Plánky",
                "ordering": ["site", "order", "name"],
            },
        ),
    ]
