"""Nefakturovana cast najmu se presouva z Karty na Plochu karty.

Najemne neni Trida a nema Klice (Tridy resi jen energie a sluzby, viz
konverzace s Danielem 2026-08-19) - patri primo ke konkretni Plose
v sekci "Plochy a najemne", ne jako zvlastni pole na Karte. Puvodni
pole na Karte prislo o den driv (migrace 0067) a bylo hned zrejme, ze
sedi na spatnem miste.

Hodnoty se prenasi na PRVNI Plochu karty (podle poradi vzniku). Kdyz
karta plochu nema, hodnota by se ztratila - takova karta ale zadny
najem nema, takze u ni nefakturovana cast nedava smysl; pro jistotu se
takovy pripad vypise do logu migrace.

Rucne psana migrace - makemigrations v tomhle repu navrhuje i
nesouvisejici stare drifty (viz pamet projektu).
"""
from decimal import Decimal

from django.db import migrations, models


def prenest_na_plochy(apps, schema_editor):
    ClientCard = apps.get_model("core", "ClientCard")
    for card in ClientCard.objects.exclude(rent_not_invoiced=Decimal("0")):
        prvni = card.card_units.order_by("pk").first()
        if prvni is None:
            print(
                f"  UPOZORNENI: karta {card.pk} ma nefakturovanou cast "
                f"{card.rent_not_invoiced}, ale zadnou Plochu - hodnota zahozena."
            )
            continue
        prvni.rent_not_invoiced = card.rent_not_invoiced
        prvni.save(update_fields=["rent_not_invoiced"])


def zpet_na_karty(apps, schema_editor):
    """Zpetny prevod - soucet Ploch zpatky na Kartu, aby sla migrace vratit."""
    ClientCard = apps.get_model("core", "ClientCard")
    for card in ClientCard.objects.all():
        celkem = sum(
            (cu.rent_not_invoiced or Decimal("0") for cu in card.card_units.all()),
            Decimal("0"),
        )
        if celkem:
            card.rent_not_invoiced = celkem
            card.save(update_fields=["rent_not_invoiced"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0067_karta_nefakturovana_cast_najmu"),
    ]

    operations = [
        migrations.AddField(
            model_name="cardunit",
            name="rent_not_invoiced",
            field=models.DecimalField(
                "Nefakturovaná část (Kč/měsíc)",
                max_digits=10,
                decimal_places=2,
                default=Decimal("0"),
                help_text=(
                    "Část měsíčního nájmu za tuto plochu, kterou klient platí bez "
                    "dokladu - do nájmu a sestav se počítá dál, ale NEfakturuje se "
                    "a nevstupuje do koeficientu DPH (není zdanitelné plnění). "
                    "Nech 0, pokud se fakturuje celý nájem."
                ),
            ),
        ),
        migrations.RunPython(prenest_na_plochy, zpet_na_karty),
        migrations.RemoveField(
            model_name="clientcard",
            name="rent_not_invoiced",
        ),
    ]
