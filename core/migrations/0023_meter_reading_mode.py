from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0022_servicepoolitem_default_amount_czk"),
    ]

    operations = [
        migrations.AddField(
            model_name="meter",
            name="reading_mode",
            field=models.CharField(
                verbose_name="Způsob zadávání odečtů",
                max_length=20,
                choices=[
                    ("state", "Stavy (kumulativní odečet, spotřeba = rozdíl mezi obdobími)"),
                    ("consumption", "Spotřeba za období (dodavatel hlásí rovnou spotřebu, ne stav)"),
                ],
                default="state",
                help_text=(
                    "Vetsina meridel hlasi kumulativni Stav (spotreba se dopocita jako "
                    "rozdil vuci minulemu obdobi). Pokud dodavatel hlasi rovnou Spotrebu "
                    "za obdobi (napr. hlavni odberne misto elektro), prepni na tento rezim "
                    "- pak staci zadat odecet jen za aktualni obdobi, hodnota se pouzije primo."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="meterreading",
            name="value",
            field=models.DecimalField(
                verbose_name="Stav / spotřeba",
                max_digits=14,
                decimal_places=3,
                help_text="Podle nastaveni mericí: bud kumulativni stav, nebo rovnou spotreba za obdobi.",
            ),
        ),
    ]
