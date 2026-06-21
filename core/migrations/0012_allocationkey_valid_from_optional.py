from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_meter_servicepoolitem_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="allocationkey",
            name="valid_from",
            field=models.DateField(blank=True, null=True, verbose_name="Platnost od"),
        ),
    ]
