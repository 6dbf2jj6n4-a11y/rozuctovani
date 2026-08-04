from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0041_diacritika_popisku"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicepoolitem",
            name="weight_unit_label",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Kratky popis, co hodnota Klice typu 'Podle vahy' na teto "
                    "polozce znamena - napr. 'm2', 'počet osob'. Pouzije se jen "
                    "u klicu BEZ vlastniho napojeneho meridla (ty maji prednost "
                    "Meter.weight_unit_label - jedna polozka muze mit vic "
                    "ruznych vazenych skupin s ruznym vyznamem vahy, napr. "
                    "'hlavní odběr elektro FM'). Jen informativni, na samotny "
                    "vypocet nema vliv."
                ),
                max_length=100,
                verbose_name="Co je váhou (u klíčů 'Podle váhy' bez vlastního měřidla)",
            ),
        ),
    ]
