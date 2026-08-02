"""
Jednorazova oprava: nastavi hodnotu klice typu "Podle váhy" u
"úklidové služby společných prostor NJ" a "odvoz komunálního odpadu NJ"
na skutecny soucet m2 karty (soucet CardUnit.area_m2 pres vsechny Plochy
karty) - Daniel potvrdil, ze u techto dvou polozek ma vaha VZDY
odpovidat vymere. Zjisteno pres diag_vahy_vs_m2: 4 karty maly
pozustatkovou hodnotu "1" misto skutecne vymery (Delphia MORAVIA,
Maker Inspiration, MastrCrane Production, Michal Gnes), FSL CZ mel
navic spatnou hodnotu jen u úklidu (423 misto 432).

BEZ --provest jen VYPISE, co by zmenil. S --provest ulozi.

Pouziti:
  python manage.py oprava_vahy_vs_m2            # jen nahled
  python manage.py oprava_vahy_vs_m2 --provest   # skutecne ulozi
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.models import AllocationKey, ServicePoolItem

ITEM_NAMES = [
    "úklidové služby společných prostor NJ",
    "odvoz komunálního odpadu NJ",
]


class Command(BaseCommand):
    help = 'Nastaví hodnotu klíčů "Podle váhy" u úklidu/odpadu NJ na skutečný součet m² karty.'

    def add_arguments(self, parser):
        parser.add_argument("--provest", action="store_true", help="Skutečně uložit (jinak jen náhled).")

    def handle(self, *args, **options):
        to_fix = []

        for name in ITEM_NAMES:
            item = ServicePoolItem.objects.filter(name=name).first()
            if item is None:
                self.stdout.write(self.style.ERROR(f'Položka "{name}" nenalezena.'))
                continue

            keys = (
                AllocationKey.objects.filter(
                    service_item=item, allocation_type=AllocationKey.AllocationType.WEIGHTED_COUNT
                )
                .select_related("client_card__client")
                .prefetch_related("client_card__card_units__unit")
            )
            for key in keys:
                area_sum = sum((cu.area_m2 or Decimal("0")) for cu in key.client_card.card_units.all())
                if key.value != area_sum:
                    to_fix.append((item, key, area_sum))

        if not to_fix:
            self.stdout.write(self.style.SUCCESS("Žádné neshody nenalezeny - nic k opravě."))
            return

        self.stdout.write(self.style.WARNING(f"Nalezeno {len(to_fix)} klíčů k opravě:"))
        for item, key, area_sum in to_fix:
            self.stdout.write(
                f"  {item.name}: {key.client_card.client.name} ({key.client_card}): "
                f"{key.value} -> {area_sum}"
            )

        if options["provest"]:
            for _, key, area_sum in to_fix:
                key.value = area_sum
                key.save(update_fields=["value"])
            self.stdout.write(self.style.SUCCESS(f"\nUpraveno {len(to_fix)} klíčů."))
        else:
            self.stdout.write(self.style.WARNING("\nToto byl jen náhled. Pro uložení spusť s --provest."))
