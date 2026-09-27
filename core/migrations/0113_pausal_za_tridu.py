"""Polozka zasobniku muze byt "Pausal za celou Tridu" - drzi jen pausal
za vsechny polozky Tridy (O_PAUSAL v NJ), report Pausalni klienti ho
porovna se skutecnymi naklady cele Tridy. Daniel 2026-09-27."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0112_radek_fakturovany_a_nefakturovany"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicepoolitem",
            name="pausal_tridy",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Položka nemá vlastní náklad - drží jen paušál, který klient platí za "
                    "všechny položky své Třídy dohromady (např. paušál za ostatní služby: "
                    "úklid, odpad, sníh...). Report Paušální klienti pak porovná tenhle "
                    "paušál se skutečnými náklady celé Třídy. Nastav i Výchozí částku 0 Kč, "
                    "jinak se položka bez nákladu v rozúčtování přeskočí."
                ),
                verbose_name="Paušál za celou Třídu",
            ),
        ),
    ]
