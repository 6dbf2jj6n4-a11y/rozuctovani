"""Prejmenovani modelu Unit: "Pronajimany prostor" -> "Predmet najmu".

Vytahy (VYTAH D, VYTAH F na FM) nejsou plocha ani prostor, presto se
pronajimaji - stejne jako venkovni plochy. "Predmet najmu" pokryje
vsechno a sedi na terminologii smlouvy, ktera uz ma clanek "Vymezeni
predmetu a ucelu najmu" (viz Site.lease_subject_text).

Meni se jen popisek v adminu, zadny sloupec v databazi.
Viz Daniel 2026-08-26.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0088_nazvy_typu_rozpoctu"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="unit",
            options={
                "ordering": ["site", "name"],
                "verbose_name": "Předmět nájmu",
                "verbose_name_plural": "Předměty nájmu",
            },
        ),
    ]
