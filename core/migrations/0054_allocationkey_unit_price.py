from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0053_alter_supplypoint_legal_loss_pct_help"),
    ]

    operations = [
        migrations.AddField(
            model_name="allocationkey",
            name="unit_price",
            field=models.DecimalField(
                null=True,
                blank=True,
                max_digits=12,
                decimal_places=4,
                help_text=(
                    "Jen pro typ 'Dle výměry (m²)'. Dohodnutá cena Kč/m²/rok pro TUTO "
                    "kartu - přebíjí cenu z Ceníku položky (např. individuálně sjednaný "
                    "paušál). Nech prázdné, aby se použila cena z Ceníku (implicitní "
                    "default). Měsíční částka = Hodnota (m²) × tato cena / 12."
                ),
                verbose_name="Cena za m²/rok (přebíjí Ceník)",
            ),
        ),
    ]
