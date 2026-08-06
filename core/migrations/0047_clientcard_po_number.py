from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0046_remove_unit_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientcard",
            name="po_number_rent",
            field=models.CharField(
                blank=True,
                help_text="Někteří klienti vyžadují uvést na faktuře za nájemné - vázané na tuto Kartu.",
                max_length=100,
                verbose_name="Číslo objednávky - nájemné",
            ),
        ),
        migrations.AddField(
            model_name="clientcard",
            name="po_number_services",
            field=models.CharField(
                blank=True,
                help_text="Někteří klienti vyžadují uvést na faktuře/vyúčtování za energie a služby - vázané na tuto Kartu.",
                max_length=100,
                verbose_name="Číslo objednávky - energie a služby",
            ),
        ),
    ]
