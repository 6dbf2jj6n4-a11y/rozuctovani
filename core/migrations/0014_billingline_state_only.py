import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Tabulka core_billingline uz v databazi existuje (vznikla drive
    mimo historii migraci). Tato migrace pouze informuje Django o
    existenci modelu (stav), aniz by se pokousela tabulku znovu
    vytvaret v databazi - proto SeparateDatabaseAndState s prazdnymi
    database_operations.
    """

    dependencies = [
        ("core", "0013_costentry"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="BillingLine",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("amount", models.DecimalField(decimal_places=2, max_digits=14, verbose_name="Částka (Kč)")),
                        ("share", models.DecimalField(blank=True, decimal_places=6, max_digits=8, null=True, verbose_name="Podíl")),
                        ("calc_detail", models.JSONField(blank=True, default=dict, verbose_name="Detail výpočtu")),
                        ("client_card", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="billing_lines", to="core.clientcard", verbose_name="Karta klienta")),
                        ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="billing_lines", to="core.period", verbose_name="Období")),
                        ("service_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="billing_lines", to="core.servicepoolitem", verbose_name="Položka zásobníku")),
                    ],
                    options={
                        "verbose_name": "Vyúčtovaná položka",
                        "verbose_name_plural": "Vyúčtované položky",
                        "ordering": ["-period", "client_card", "service_item"],
                        "unique_together": {("client_card", "period", "service_item")},
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
