import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_billingline_units"),
    ]

    operations = [
        migrations.AddField(
            model_name="period",
            name="date_from",
            field=models.DateField(
                verbose_name="Začátek období",
                null=True,
                blank=True,
                help_text="Vyplní se automaticky z roku/měsíce. Upravte pro nestandardní období.",
            ),
        ),
        migrations.AddField(
            model_name="period",
            name="date_to",
            field=models.DateField(
                verbose_name="Konec období",
                null=True,
                blank=True,
                help_text="Vyplní se automaticky z roku/měsíce. Upravte pro nestandardní období.",
            ),
        ),
    ]
