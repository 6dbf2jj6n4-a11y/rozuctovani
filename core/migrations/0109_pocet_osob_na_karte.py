"""Pocet osob na Karte a zdroj vahy "Pocet osob z karty".

Osoby patri klientovi, ne mistnosti - klice na vodu, teplou vodu nebo
uklid si z nej vahu vezmou samy a zadava se jednou za kartu. Prvni krok
prestavby vah (vaha odvozena z Ploch a z Karty, ne rucni cislo).
Viz Daniel 2026-09-25."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0108_napojeni_ucetnictvi"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientcard",
            name="pocet_osob",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Počet osob",
                help_text=(
                    "Kolik lidí klient v pronajatých prostorách má. Klíče s váhou "
                    "„Počet osob z karty“ (voda, teplá voda, úklid…) si ho vezmou "
                    "samy - zadává se jednou za kartu, ne u každého klíče."
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
