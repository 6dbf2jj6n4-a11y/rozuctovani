from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0056_invoiceclasscolor"),
    ]

    operations = [
        migrations.AddField(
            model_name="period",
            name="is_current",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Období, se kterým se právě pracuje - předvyplní se ve všech "
                    "sestavách. Není to totéž co kalendářní měsíc: v srpnu se běžně "
                    "rozúčtovává červenec. Aktuální může být vždy jen jedno období, "
                    "zaškrtnutím se ostatní automaticky odznačí."
                ),
                verbose_name="Aktuální období",
            ),
        ),
    ]
