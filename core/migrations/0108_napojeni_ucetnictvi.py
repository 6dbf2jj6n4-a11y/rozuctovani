"""Napojeni na ucetnictvi a kopie PDF podkladovych faktur na R2.

Portal uz neberou PDF primo z ABRA, ale z vlastni kopie na R2 - kdyby se
ucetni system jednou zmenil nebo zrusil, stare faktury v portalu
zustanou. U jineho systemu nez ABRA se faktury nahravaji rucne, proto
flexi_id muze byt prazdne. Viz Daniel 2026-09-25."""
from django.db import migrations, models

import core.models
import core.storage


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0107_podkladova_faktura"),
    ]

    operations = [
        migrations.CreateModel(
            name="NapojeniUcetnictvi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("system", models.CharField(
                    choices=[
                        ("abra_flexi", "ABRA Flexi – faktury se dotahují z účetnictví"),
                        ("rucne", "Jiný systém – faktury se nahrávají ručně"),
                    ],
                    default="abra_flexi",
                    help_text=(
                        "ABRA Flexi: u Období akce „Dotáhnout podkladové faktury z ABRA“ "
                        "faktury najde, propojí s položkami a PDF zkopíruje do úložiště.\n"
                        "Jiný systém: faktury se přidávají ručně v Nastavení → Podkladové "
                        "faktury (nahraje se PDF). Ručně jde přidat i s ABRA, třeba pelety."
                    ),
                    max_length=20, verbose_name="Účetní systém",
                )),
            ],
            options={
                "verbose_name": "Napojení na účetnictví",
                "verbose_name_plural": "Napojení na účetnictví",
            },
        ),
        migrations.AlterField(
            model_name="podkladovafaktura",
            name="flexi_id",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="ID faktury v ABRA",
                help_text="Vyplněno u faktur dotažených z ABRA, u ručně nahraných prázdné.",
            ),
        ),
        migrations.AlterField(
            model_name="podkladovafaktura",
            name="nazev_souboru",
            field=models.CharField(blank=True, max_length=255, verbose_name="Název souboru"),
        ),
        migrations.AlterField(
            model_name="podkladovafaktura",
            name="nacteno",
            field=models.DateTimeField(auto_now=True, verbose_name="Naposledy změněno"),
        ),
        migrations.AddField(
            model_name="podkladovafaktura",
            name="soubor",
            field=models.FileField(
                blank=True, storage=core.storage.R2MediaStorage(),
                upload_to=core.models._cesta_podkladove_faktury, verbose_name="PDF faktury",
            ),
        ),
    ]
