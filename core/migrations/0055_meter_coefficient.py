from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0054_allocationkey_unit_price"),
    ]

    operations = [
        migrations.AddField(
            model_name="meter",
            name="coefficient",
            field=models.DecimalField(
                default=Decimal("1"),
                max_digits=12,
                decimal_places=6,
                help_text=(
                    "Násobitel odečtu pro převod na měrnou jednotku měřidla. Např. teplo "
                    "měřené v kWh, ale vykazované v GJ: koeficient = 0,0036 "
                    "(1 GJ = 277,778 kWh). Výchozí 1 = beze změny. Poměry mezi kartami "
                    "(a tím rozúčtované Kč) se nemění, mění se jen jednotky/čísla."
                ),
                verbose_name="Koeficient (odečet × koef. = spotřeba)",
            ),
        ),
    ]
