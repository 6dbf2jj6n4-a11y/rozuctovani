from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_clientcard_unit_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="unit",
            name="code",
            field=models.CharField(blank=True, max_length=50, verbose_name="Kód / označení"),
        ),
        migrations.AddField(
            model_name="unit",
            name="purpose",
            field=models.CharField(blank=True, max_length=100, verbose_name="Účel"),
        ),
        migrations.AddField(
            model_name="unit",
            name="rate_per_m2_year",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name="Sazba Kč/m²/rok"),
        ),
        migrations.AddField(
            model_name="unit",
            name="unit_type",
            field=models.CharField(blank=True, default="m2", max_length=10, verbose_name="Jednotka"),
        ),
    ]
