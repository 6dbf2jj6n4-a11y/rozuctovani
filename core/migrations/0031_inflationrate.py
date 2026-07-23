from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_allocationkey_area_price"),
    ]

    operations = [
        migrations.CreateModel(
            name="InflationRate",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.PositiveIntegerField(unique=True, verbose_name="Rok")),
                ("percent", models.DecimalField(decimal_places=2, max_digits=5, verbose_name="Míra inflace (%)")),
            ],
            options={
                "verbose_name": "Míra inflace",
                "verbose_name_plural": "Míry inflace",
                "ordering": ["-year"],
            },
        ),
    ]
