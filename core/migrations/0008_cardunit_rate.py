from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_clientcard_is_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="cardunit",
            name="rate_per_m2",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name="Cena Kč/m²/rok"),
        ),
    ]
