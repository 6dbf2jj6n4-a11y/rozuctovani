"""Pocet osob pro TUV na Karte a zdroj vahy "Pocet osob pro TUV z karty".

Teplou vodu nepouziva vzdy cely tym. Kdyz pole zustane prazdne, plati
celkovy Pocet osob. Viz Daniel 2026-09-25."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0109_pocet_osob_na_karte"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientcard",
            name="pocet_osob_tuv",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Počet osob pro TUV",
                help_text=(
                    "Kolik lidí používá teplou vodu. Klíče s váhou „Počet osob pro "
                    "TUV z karty“ si ho vezmou samy. Nech prázdné, když je stejný "
                    "jako Počet osob."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="allocationkey",
            name="weight_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Hodnota zadaná ručně"),
                    ("plocha", "Celá plocha karty (m²)"),
                    ("vytapena", "Vytápěná plocha karty (m²)"),
                    ("osoby", "Počet osob z karty"),
                    ("osoby_tuv", "Počet osob pro TUV z karty"),
                ],
                default="", max_length=20, verbose_name="Odkud brát váhu",
                help_text=(
                    "Místo pevné Hodnoty se váha spočítá z Ploch téhle Karty a "
                    "přepočítá se sama při každém rozúčtování - nerozejde se, když "
                    "se plocha přidá, ubere nebo se opraví výměra. „Celá plocha“ je "
                    "pro služby placené podle velikosti pronajatého (ostraha, odvoz "
                    "odpadu, úklid sněhu), „Vytápěná plocha“ pro teplo, „Počet osob“ "
                    "(z pole na Kartě) pro vodu, teplou vodu a úklid. Když má "
                    "karta na jedné položce takových klíčů víc, váha se započítá "
                    "jen JEDNOU - klíče doplněné automaticky k plochám tak nemůžou "
                    "nic zdvojit."
                ),
            ),
        ),
    ]
