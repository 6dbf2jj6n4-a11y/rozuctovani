from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0038_simplify_allocation_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicepoolitem",
            name="weight_unit_label",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Kratky popis, co hodnota klice typu 'Podle vahy' na teto polozce "
                    "znamena - napr. 'm2', 'počet osob', 'počet radiátorů'. Jen "
                    "informativni (zobrazuje se v adminu a v Karte klienta), na "
                    "samotny vypocet nema vliv."
                ),
                max_length=100,
                verbose_name="Co je váhou (u typu 'Podle váhy')",
            ),
        ),
    ]
