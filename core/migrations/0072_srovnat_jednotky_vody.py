"""Srovnani jednotek u vodomeru.

Dve veci nalezene pri kontrole jednotek (konverzace s Danielem
2026-08-19):

1. W_FM_CELKEM (FM, celkova spotreba vody) mel jednotku "kWh" - zustala
   tam vychozi hodnota pole `Meter.unit_of_measure` (default="kWh"),
   ktera se pri zalozeni neprepsala.
2. Vsech 23 vodomeru pouzivalo "m3" bez horniho indexu, zatimco Trida
   Voda ma vychozi "m³". Kvuli tomu se v odectech i sestavach ukazovalo
   "m3".

Migrace srovna oboji na "m³". Cili se jen na hodnoty, ktere jsme
skutecne nasli ("m3" a "kWh"), aby se neprepsala pripadna zamerne
zadana jina jednotka. Na vypocty to vliv nema - zadny kod se na
konkretni retezec jednotky neptá (jedina vyjimka je porovnani na "m²"
v billing/statement_generator.py, coz je plocha, ne voda).

Rucne psana migrace - makemigrations v tomhle repu navrhuje i
nesouvisejici stare drifty (viz pamet projektu).
"""
from django.db import migrations

SPRAVNA = "m³"
OPRAVOVANE = ["m3", "kWh"]


def srovnat(apps, schema_editor):
    Meter = apps.get_model("core", "Meter")
    qs = Meter.objects.filter(meter_type="voda", unit_of_measure__in=OPRAVOVANE)
    pocet = qs.count()
    qs.update(unit_of_measure=SPRAVNA)
    print(f"  Jednotka vodomeru srovnana na '{SPRAVNA}': {pocet} meridel")


def zpet(apps, schema_editor):
    """Zpetne jen na 'm3' - puvodni chybne 'kWh' u jednoho meridla se
    nevraci, to byla chyba, ne stav, ke kteremu je proc se vracet."""
    Meter = apps.get_model("core", "Meter")
    Meter.objects.filter(meter_type="voda", unit_of_measure=SPRAVNA).update(unit_of_measure="m3")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0071_meridlo_jednotka_odectu"),
    ]

    operations = [
        migrations.RunPython(srovnat, zpet),
    ]
