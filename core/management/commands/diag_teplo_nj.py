"""
Diagnostika: vypise vsechny polozky tridy "Teplo" (a jejich klice) pro
NJ (a pro srovnani i FM) - hledame, jestli existuje "sesterska" polozka
k "teplo - spotreba pelet NJ" s uz spravne nastavenymi klici, ze ktere
by se dalo vychazet.

Pouziti:
  python manage.py diag_teplo_nj
"""
from django.core.management.base import BaseCommand

from core.models import ServicePoolItem


class Command(BaseCommand):
    help = "Vypíše položky třídy Teplo a jejich klíče pro všechny areály."

    def handle(self, *args, **options):
        items = ServicePoolItem.objects.filter(invoice_class="teplo").select_related("site", "meter").order_by("site__name", "name")
        for item in items:
            self.stdout.write(self.style.WARNING(f"\n--- {item} (měřidlo: {item.meter}) ---"))
            keys = item.allocation_keys.select_related("client_card__client").all()
            if not keys:
                self.stdout.write("  žádné klíče")
                continue
            for key in keys:
                self.stdout.write(
                    f"  {key.client_card.client.name}: {key.get_allocation_type_display()} "
                    f"hodnota={key.value} fakturovat={key.is_billed}"
                )
