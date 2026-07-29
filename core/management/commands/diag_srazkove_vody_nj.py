"""
Diagnostika pred prevodem "srazkove vody NJ" z Pevne castky na
Plocha x cena/m2: pro kazdeho klienta s klicem u teto polozky vypise
soucasnou pevnou castku a jeho aktualni celkovou vymeru (CardUnit,
vcetne area_m2_override) - pro kontrolu pred prevodem.

Pouziti:
  python manage.py diag_srazkove_vody_nj
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.models import ServicePoolItem


class Command(BaseCommand):
    help = "Vypíše klienty položky srážkové vody NJ s jejich pevnou částkou a aktuální výměrou."

    def handle(self, *args, **options):
        item = ServicePoolItem.objects.filter(name__icontains="srážkové vody", site__name__icontains="NJ").first()
        if item is None:
            self.stdout.write(self.style.ERROR("Položka 'srážkové vody NJ' nenalezena."))
            return

        keys = item.allocation_keys.select_related("client_card__client").all()
        for key in keys:
            card = key.client_card
            total_area = sum(
                ((cu.area_m2_override if cu.area_m2_override is not None else cu.unit.area_m2) or Decimal("0"))
                for cu in card.card_units.select_related("unit").all()
            )
            self.stdout.write(
                f"{card.client.name:<35} typ={key.get_allocation_type_display():<25} "
                f"hodnota={key.value!s:<10} plocha_celkem={total_area} m² fakturovat={key.is_billed}"
            )
