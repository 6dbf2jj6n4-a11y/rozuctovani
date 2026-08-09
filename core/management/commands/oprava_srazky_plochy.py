"""
Nastavi hodnotu klice typu "Dle výměry (m²)" u polozek "srážkové vody"
(vsechny arealy) na skutecny soucet m2 karty (soucet CardUnit.area_m2
pres vsechny Plochy karty) - Daniel potvrdil 2026-08-09, ze se ma pouzit
soucet ploch vsude, i tam, kde uz byla drive nastavena jina hodnota
(napr. FM melo u vetsiny klientu jen ~80 % souctu ploch).

BEZ --provest jen VYPISE, co by zmenil. S --provest ulozi.

Pouziti:
  python manage.py oprava_srazky_plochy            # jen nahled
  python manage.py oprava_srazky_plochy --provest   # skutecne ulozi
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.models import AllocationKey, ServicePoolItem


class Command(BaseCommand):
    help = 'Nastaví hodnotu klíčů "Dle výměry" u srážkové vody (všechny areály) na skutečný součet m² karty.'

    def add_arguments(self, parser):
        parser.add_argument("--provest", action="store_true", help="Skutečně uložit (jinak jen náhled).")

    def handle(self, *args, **options):
        to_fix = []

        items = ServicePoolItem.objects.filter(name__icontains="srážkové vody").select_related("site")
        for item in items:
            keys = (
                AllocationKey.objects.filter(
                    service_item=item, allocation_type=AllocationKey.AllocationType.AREA_PRICE
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
                f"  {item.name} ({item.site}): {key.client_card.client.name} ({key.client_card}): "
                f"{key.value} -> {area_sum}"
            )

        if options["provest"]:
            for _, key, area_sum in to_fix:
                key.value = area_sum
                key.save(update_fields=["value"])
            self.stdout.write(self.style.SUCCESS(f"\nUpraveno {len(to_fix)} klíčů."))
        else:
            self.stdout.write(self.style.WARNING("\nToto byl jen náhled. Pro uložení spusť s --provest."))
