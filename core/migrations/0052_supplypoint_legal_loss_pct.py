from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0051_supplypoint"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplypoint",
            name="legal_loss_pct",
            field=models.DecimalField(
                default=Decimal("0"),
                max_digits=5,
                decimal_places=2,
                help_text=(
                    "Zákonná (systémová) ztráta, kterou dodavatel účtuje navíc - "
                    "typicky 4 % u velkoodběru. Naměřené hodnoty se porovnávají s "
                    "fakturovanou spotřebou až PO odečtení těchto % (reálně dodané "
                    "= faktura × (1 − %/100)); do vyúčtování se klientům ztráta "
                    "vrací. Co zůstane po odečtení této i naměřené spotřeby jsou "
                    "skutečné ztráty (proměření / pozdní odečet). 0 = nepoužít "
                    "(např. EAN 668, kde čteme vlastní měřidla)."
                ),
                verbose_name="Zákonná ztráta %",
            ),
        ),
    ]
