"""Karta muze mit na polozce za obdobi dva radky vyuctovani - fakturovany
a nefakturovany (pausal + skutecny podil, ktery nese pronajimatel). Viz
billing/engine.py, 3) sestaveni vysledku."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0111_osoby_tuv_bez_dosazeni"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="billingline",
            unique_together={("client_card", "period", "service_item", "is_billed")},
        ),
        migrations.AlterModelOptions(
            name="billingline",
            options={
                "ordering": ["-period", "client_card", "service_item", "-is_billed"],
                "verbose_name": "Vyúčtovaná položka",
                "verbose_name_plural": "Vyúčtované položky",
            },
        ),
    ]
