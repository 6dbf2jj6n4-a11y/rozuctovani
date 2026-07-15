from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_pricelist_costentry_update"),
    ]

    operations = [
        migrations.AddField(
            model_name="billingline",
            name="units",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=14,
                null=True,
                verbose_name="Množství (jednotky)",
                help_text="Přidělené jednotky (kWh, m³...) včetně poměrných ztrát.",
            ),
        ),
    ]
