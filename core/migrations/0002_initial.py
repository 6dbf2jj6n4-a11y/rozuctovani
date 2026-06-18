from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="code",
            field=models.CharField(blank=True, max_length=20, unique=True, verbose_name="Kód", default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="client",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="Aktivní"),
        ),
        migrations.AddField(
            model_name="client",
            name="is_landlord",
            field=models.BooleanField(default=False, verbose_name="Pronajímatel"),
        ),
        migrations.AddField(
            model_name="client",
            name="street",
            field=models.CharField(blank=True, max_length=200, verbose_name="Ulice"),
        ),
        migrations.AddField(
            model_name="client",
            name="street_number",
            field=models.CharField(blank=True, max_length=20, verbose_name="Číslo"),
        ),
        migrations.AddField(
            model_name="client",
            name="zip_code",
            field=models.CharField(blank=True, max_length=10, verbose_name="PSČ"),
        ),
        migrations.AddField(
            model_name="client",
            name="city",
            field=models.CharField(blank=True, max_length=100, verbose_name="Město"),
        ),
        migrations.AddField(
            model_name="client",
            name="vat_payer",
            field=models.BooleanField(default=False, verbose_name="Plátce DPH"),
        ),
        migrations.AddField(
            model_name="client",
            name="bank_name",
            field=models.CharField(blank=True, max_length=50, verbose_name="Banka"),
        ),
        migrations.AddField(
            model_name="client",
            name="bank_account",
            field=models.CharField(blank=True, max_length=50, verbose_name="Číslo účtu"),
        ),
        migrations.AddField(
            model_name="client",
            name="bank_code",
            field=models.CharField(blank=True, max_length=10, verbose_name="Kód banky"),
        ),
        migrations.AlterField(
            model_name="client",
            name="ico",
            field=models.CharField(blank=True, max_length=20, verbose_name="IČO"),
        ),
        migrations.AlterField(
            model_name="client",
            name="dic",
            field=models.CharField(blank=True, max_length=20, verbose_name="DIČ"),
        ),
    ]
