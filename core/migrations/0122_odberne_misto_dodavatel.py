from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0121_klient_datum_narozeni"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplypoint",
            name="supplier",
            field=models.CharField(
                blank=True,
                help_text="Kdo za tenhle odběr fakturuje (např. TEDOM, VEOLIA, SMVAK). Nově založený Náklad položky z pole „Náklad (faktura) tohoto odběru“ ho převezme do „Dodavatel / zdroj“ sám.",
                max_length=100,
                verbose_name="Dodavatel",
            ),
        ),
    ]
