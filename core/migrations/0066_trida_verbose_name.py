"""Trida uz neni jen o barvach - prejmenovani v adminu + doladeni defaultu.

Trida ridi i sekce v Karte klienta, zarazeni Meridel a Odbernych mist,
takze puvodni "Třídy (barvy a paušály)" uz sedelo spatne. Zaroven se
polozka v menu presunula z Nastaveni do sekce Arealy/Objekty jako
samostatna tabulka (config/settings.py) - na Danielovu zadost.

Zaroven se srovnavaji VYCHOZI hodnoty poli na ceske kody Trid - migrace
0064 prepsala data, ale v migracnim stavu zustaly stare anglicke defaulty
("other" / "electricity"). Django bere default z modelu, takze to nic
nerozbijelo, jen by to navzdy hlasilo rozdil oproti modelum.

Jen popisky a defaulty, na data ani schema to nema vliv.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0065_trida_ma_sekci_klicu"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="invoiceclasscolor",
            options={
                "ordering": ["sort_order", "invoice_class"],
                "verbose_name": "Třída",
                "verbose_name_plural": "Třídy",
            },
        ),
        migrations.AlterField(
            model_name="servicepoolitem",
            name="invoice_class",
            field=models.CharField(default="ostatni", max_length=20, verbose_name="Třída"),
        ),
        migrations.AlterField(
            model_name="supplypoint",
            name="meter_type",
            field=models.CharField(default="elektro", max_length=20, verbose_name="Třída"),
        ),
    ]
