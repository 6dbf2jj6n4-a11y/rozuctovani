from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0115_dokumenty_na_r2"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceclasscolor",
            name="ztraty_do_jednotek",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Jen jak se rozdíl mezi fakturovaným a naměřeným množstvím "
                    "(ztráty, společné prostory) UKÁŽE ve vyúčtování - částky klientům "
                    "jsou v obou případech stejné. Vypnuto (výchozí): naměřené jednotky "
                    "× upravená cena (náklad ÷ naměřené). Zapnuto: jednotky navýšené "
                    "o podíl na rozdílu × cena z faktury dodavatele."
                ),
                verbose_name="Ztráty rozpouštět do jednotek",
            ),
        ),
    ]
