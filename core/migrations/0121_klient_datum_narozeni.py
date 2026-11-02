# Fyzicka osoba se ve Smlouve identifikuje datem narozeni. Daniel 2026-11-02.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0120_meridlo_obsluhovane_prostory"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="birth_date",
            field=models.DateField(blank=True, null=True, verbose_name="Datum narození"),
        ),
    ]
