import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_clientcard_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="CardUnit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("card", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="card_units", to="core.clientcard", verbose_name="Karta")),
                ("unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="card_units", to="core.unit", verbose_name="Plocha")),
            ],
            options={"verbose_name": "Plocha karty", "verbose_name_plural": "Plochy karty", "unique_together": {("card", "unit")}},
        ),
    ]
