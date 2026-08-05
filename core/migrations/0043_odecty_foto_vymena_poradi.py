from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0042_servicepoolitem_weight_unit_label_fallback"),
    ]

    operations = [
        migrations.AddField(
            model_name="meter",
            name="display_order",
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    "Určuje pořadí měřidel na obrazovce pro zadávání odečtů. "
                    "Stejná hodnota (výchozí 0) řadí abecedně podle kódu."
                ),
                verbose_name="Pořadí při zadávání odečtů",
            ),
        ),
        migrations.AddField(
            model_name="meterreading",
            name="photo",
            field=models.ImageField(
                blank=True, null=True, upload_to="odecty/%Y/%m/", verbose_name="Foto odečtu"
            ),
        ),
        migrations.AddField(
            model_name="meterreading",
            name="reset_from_value",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                help_text=(
                    "Vyplnit jen při výměně měřidla za nové - stav v poli 'Stav / "
                    "spotřeba' pak patří novému přístroji a spotřeba se počítá od "
                    "tohoto počátečního stavu (obvykle 0), ne od minulého odečtu "
                    "starého měřidla. Viz Meter.consumption_for."
                ),
                max_digits=14,
                null=True,
                verbose_name="Počáteční stav (výměna měřidla)",
            ),
        ),
    ]
