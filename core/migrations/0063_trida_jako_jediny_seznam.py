"""Trida se stava JEDINYM seznamem pro Polozky, Meridla i Odberna mista.

Do ted byly dva nezavisle vycty pro skoro totez: Meter.MeterType (Typ
meridla) a ServicePoolItem.InvoiceClass (Trida). Lisily se jen v tom, ze
"Plyn" byl typ bez vlastni tridy a "Nájemné" trida bez meridel. Daniel
na tu duplicitu upozornil 2026-08-18, takze Typy meridel (MeterTypeConfig,
zalozene o migraci driv) rusime uplne - meridlo si vybira primo Tridu.

Data se prevadet nemusi: hodnoty v Meter.meter_type i SupplyPoint.meter_type
(electricity/water/heat/other) uz presne odpovidaji kodum Trid. Jedina
vyjimka je "gas", ktery vlastni Tridu nikdy nemel a vezl se s "other" -
pro jistotu se prepise, i kdyz v produkci na nej nevisi zadne meridlo.
"""
from django.db import migrations, models


# Poradi i nazvy odpovidaji puvodnimu ServicePoolItem.InvoiceClass enumu,
# aby se nezmenilo razeni v zadne sestave. Jednotky prebiraji z
# napevno zapsaneho slovniku, ktery driv byl v core/admin.py.
TRIDY = [
    ("rent", "Nájemné", "", 0),
    ("electricity", "Elektřina", "kWh", 1),
    ("water", "Voda", "m³", 2),
    ("heat", "Teplo", "GJ", 3),
    ("other", "Ostatní", "", 4),
]


def naplnit_tridy(apps, schema_editor):
    InvoiceClassColor = apps.get_model("core", "InvoiceClassColor")
    Meter = apps.get_model("core", "Meter")
    SupplyPoint = apps.get_model("core", "SupplyPoint")

    for code, label, unit, sort_order in TRIDY:
        InvoiceClassColor.objects.update_or_create(
            invoice_class=code,
            defaults={"label": label, "default_unit_of_measure": unit, "sort_order": sort_order},
        )

    # "Plyn" nikdy nebyl samostatna Trida - co na nem pripadne visi,
    # patri do "Ostatní" (tak se choval i drive pres METER_TYPE_TO_CLASS).
    Meter.objects.filter(meter_type="gas").update(meter_type="other")
    SupplyPoint.objects.filter(meter_type="gas").update(meter_type="other")


def vratit_nazvy(apps, schema_editor):
    """Zpetny chod: nazvy/poradi se zahodi, kody zustavaji - ty jsou
    zdrojem pravdy a shoduji se s puvodnim enumem."""
    InvoiceClassColor = apps.get_model("core", "InvoiceClassColor")
    InvoiceClassColor.objects.update(label="", default_unit_of_measure="", sort_order=0)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0062_meter_type_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceclasscolor",
            name="label",
            field=models.CharField(
                blank=True, help_text="Jak se Třída zobrazuje v adminu. Prázdné = použije se Kód.",
                max_length=50, verbose_name="Název",
            ),
        ),
        migrations.AddField(
            model_name="invoiceclasscolor",
            name="default_unit_of_measure",
            field=models.CharField(
                blank=True,
                help_text="Např. kWh, m³, GJ. Použije se v přehledu spotřeb u měřidel bez vlastní jednotky.",
                max_length=20, verbose_name="Výchozí měrná jednotka",
            ),
        ),
        migrations.AddField(
            model_name="invoiceclasscolor",
            name="sort_order",
            field=models.PositiveIntegerField(
                default=0, help_text="Určuje pořadí Tříd v sestavách a nabídkách.",
                verbose_name="Pořadí",
            ),
        ),
        migrations.AlterField(
            model_name="invoiceclasscolor",
            name="invoice_class",
            field=models.CharField(
                help_text="Interní kód - odkazují na něj Položky, Měřidla i Odběrná místa. Needitovatelný po založení.",
                max_length=20, unique=True, verbose_name="Kód",
            ),
        ),
        migrations.AlterModelOptions(
            name="invoiceclasscolor",
            options={
                "ordering": ["sort_order", "invoice_class"],
                "verbose_name": "Třída",
                "verbose_name_plural": "Třídy (barvy a paušály)",
            },
        ),
        migrations.AlterField(
            model_name="servicepoolitem",
            name="invoice_class",
            field=models.CharField(default="other", max_length=20, verbose_name="Třída"),
        ),
        migrations.AlterField(
            model_name="meter",
            name="meter_type",
            field=models.CharField(max_length=20, verbose_name="Třída"),
        ),
        migrations.AlterField(
            model_name="supplypoint",
            name="meter_type",
            field=models.CharField(default="electricity", max_length=20, verbose_name="Třída"),
        ),
        migrations.RunPython(naplnit_tridy, vratit_nazvy),
        migrations.DeleteModel(name="MeterTypeConfig"),
    ]
