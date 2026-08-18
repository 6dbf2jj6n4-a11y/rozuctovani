"""Kody Trid do cestiny: rent -> najemne, electricity -> elektro,
water -> voda, heat -> teplo, other -> ostatni.

Daniel si je vyzadal 2026-08-18 hned po sjednoceni Trid. Bez diakritiky
zamerne - kod se propisuje do nazvu CSS trid (rx-class-*, key-section-*)
a do adres filtru v adminu, kde je ASCII spolehlivejsi. Lidsky nazev
(label) se nemeni, ten uz diakritiku ma a jde prejmenovat v adminu.

Kod je jen interni odkaz - Polozky, Meridla i Odberna mista na nej
odkazuji obycejnym textem (neni to FK), takze se musi prepsat ve vsech
ctyrech tabulkach naraz.
"""
from django.db import migrations


PREJMENOVANI = [
    ("rent", "najemne"),
    ("electricity", "elektro"),
    ("water", "voda"),
    ("heat", "teplo"),
    ("other", "ostatni"),
]


def _prepsat(apps, dvojice):
    InvoiceClassColor = apps.get_model("core", "InvoiceClassColor")
    ServicePoolItem = apps.get_model("core", "ServicePoolItem")
    Meter = apps.get_model("core", "Meter")
    SupplyPoint = apps.get_model("core", "SupplyPoint")

    for stary, novy in dvojice:
        InvoiceClassColor.objects.filter(invoice_class=stary).update(invoice_class=novy)
        ServicePoolItem.objects.filter(invoice_class=stary).update(invoice_class=novy)
        Meter.objects.filter(meter_type=stary).update(meter_type=novy)
        SupplyPoint.objects.filter(meter_type=stary).update(meter_type=novy)


def do_cestiny(apps, schema_editor):
    _prepsat(apps, PREJMENOVANI)


def zpet_do_anglictiny(apps, schema_editor):
    _prepsat(apps, [(novy, stary) for stary, novy in PREJMENOVANI])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0063_trida_jako_jediny_seznam"),
    ]

    operations = [
        migrations.RunPython(do_cestiny, zpet_do_anglictiny),
    ]
