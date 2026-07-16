from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_period_date_range"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicepoolitem",
            name="default_amount_czk",
            field=models.DecimalField(
                verbose_name="Výchozí měsíční částka (Kč)",
                max_digits=12,
                decimal_places=2,
                null=True,
                blank=True,
                help_text=(
                    "Pouzije se pri vypoctu rozuctovani pro obdobi, pro ktere neni "
                    "zadany zadny Naklad za obdobi (CostEntry) - typicky pro sluzby "
                    "s neměnnou paušální cenou (ostraha, internet...), aby se nemusela "
                    "castka zadavat kazdy mesic rucne. Pokud je pro dane obdobi CostEntry "
                    "zadany, ma vzdy prednost pred touto vychozi castkou."
                ),
            ),
        ),
    ]
