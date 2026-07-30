from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0039_servicepoolitem_weight_unit_label"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="servicepoolitem",
            name="weight_unit_label",
        ),
        migrations.AddField(
            model_name="meter",
            name="weight_unit_label",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Kratky popis, co hodnota Klice typu 'Podle vahy' napojeneho na "
                    "toto meridlo znamena - napr. 'm2', 'počet osob', 'počet "
                    "radiátorů'. Typicke pro virtualni 'zbytkova' meridla jako "
                    "E_SPOL, kde se jejich spotreba deli mezi vice karet vahou. Jen "
                    "informativni (zobrazuje se v adminu a v Karte klienta), na "
                    "samotny vypocet nema vliv."
                ),
                max_length=100,
                verbose_name="Co je váhou (u klíčů 'Podle váhy' na tomto měřidle)",
            ),
        ),
    ]
