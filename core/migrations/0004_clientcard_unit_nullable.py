from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_update_unit_and_card"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clientcard",
            name="unit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cards",
                to="core.unit",
                verbose_name="Prostor",
            ),
        ),
    ]
