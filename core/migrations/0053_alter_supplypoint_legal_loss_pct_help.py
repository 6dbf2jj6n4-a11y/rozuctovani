from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    """Jen zmena help_text (oprava vzorce: realne = faktura / (1 + %/100),
    ne faktura x (1 - %/100)) - bez dopadu na schema DB."""

    dependencies = [
        ("core", "0052_supplypoint_legal_loss_pct"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supplypoint",
            name="legal_loss_pct",
            field=models.DecimalField(
                default=Decimal("0"),
                max_digits=5,
                decimal_places=2,
                help_text=(
                    "Zákonná (systémová) ztráta, kterou dodavatel účtuje navíc - "
                    "typicky 4 % u velkoodběru. Faktura už ztrátu obsahuje "
                    "(dodavatel k reálně dodanému připočítá tato %), takže reálně "
                    "dodané = faktura / (1 + %/100); do vyúčtování se klientům ztráta "
                    "vrací. Co zůstane po odečtení této i naměřené spotřeby jsou "
                    "skutečné ztráty (proměření / pozdní odečet). 0 = nepoužít "
                    "(např. EAN 668, kde čteme vlastní měřidla)."
                ),
                verbose_name="Zákonná ztráta %",
            ),
        ),
    ]
