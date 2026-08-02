"""
Diagnostika (jen cteni, nic nemeni): porovna hodnotu (vahu) klice typu
"Podle váhy" u vybranych OSTATNÍ polozek proti skutecne pronajate vymere
karty (soucet CardUnit.area_m2 pres vsechny Plochy karty) - Daniel
potvrdil, ze u "úklidové služby společných prostor NJ" a "odvoz
komunálního odpadu NJ" ma vaha VZDY odpovidat souctu m2 karty.

Pouziti:
  python manage.py diag_vahy_vs_m2
  python manage.py diag_vahy_vs_m2 --item="odvoz komunálního odpadu NJ"
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.models import AllocationKey, ServicePoolItem

DEFAULT_ITEM_NAMES = [
    "úklidové služby společných prostor NJ",
    "odvoz komunálního odpadu NJ",
]


class Command(BaseCommand):
    help = 'Porovná AllocationKey.value ("Podle váhy") proti součtu m² karty pro dané OSTATNÍ položky.'

    def add_arguments(self, parser):
        parser.add_argument("--item", action="append", default=None)

    def handle(self, *args, **options):
        item_names = options["item"] or DEFAULT_ITEM_NAMES

        for name in item_names:
            item = ServicePoolItem.objects.filter(name=name).first()
            if item is None:
                self.stdout.write(self.style.ERROR(f'Položka "{name}" nenalezena.'))
                continue

            self.stdout.write(self.style.WARNING(f"\n=== {item} ==="))

            keys = (
                AllocationKey.objects.filter(
                    service_item=item, allocation_type=AllocationKey.AllocationType.WEIGHTED_COUNT
                )
                .select_related("client_card__client")
                .prefetch_related("client_card__card_units__unit")
            )

            mismatches = 0
            for key in keys:
                card = key.client_card
                area_sum = sum((cu.area_m2 or Decimal("0")) for cu in card.card_units.all())
                ok = key.value == area_sum
                if not ok:
                    mismatches += 1
                marker = "" if ok else "  <-- NESEDÍ"
                self.stdout.write(
                    f"  {card.client.name} ({card}): klíč_hodnota={key.value} "
                    f"součet_m²_karty={area_sum} aktivní_karta={card.is_active}{marker}"
                )

            if mismatches:
                self.stdout.write(self.style.ERROR(f"\n{mismatches} klíč(ů) nesedí s aktuální výměrou karty."))
            else:
                self.stdout.write(self.style.SUCCESS("\nVšechny klíče sedí s aktuální výměrou karty."))
