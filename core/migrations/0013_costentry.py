import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_allocationkey_valid_from_optional"),
    ]

    operations = [
        migrations.CreateModel(
            name="CostEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14, verbose_name="Částka (Kč)")),
                ("note", models.CharField(blank=True, max_length=300, verbose_name="Poznámka")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cost_entries", to="core.period", verbose_name="Období")),
                ("service_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cost_entries", to="core.servicepoolitem", verbose_name="Položka zásobníku")),
            ],
            options={
                "verbose_name": "Náklad za období",
                "verbose_name_plural": "Náklady za období",
                "ordering": ["-period", "service_item"],
                "unique_together": {("service_item", "period")},
            },
        ),
    ]
