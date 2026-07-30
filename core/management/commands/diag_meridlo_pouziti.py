"""
Diagnostika (jen cteni): najde vsechny AllocationKey napojene na
meridlo s danym kodem (presna shoda i castecna, --presne pro presnou
shodu) a vypise klienty/karty/polozky, ktere ho pouzivaji.

Pouziti:
  python manage.py diag_meridlo_pouziti T_SPOL
  python manage.py diag_meridlo_pouziti T_SPOL --presne
"""
from django.core.management.base import BaseCommand

from core.models import AllocationKey, Meter


class Command(BaseCommand):
    help = "Najde klíče napojené na měřidlo s daným kódem (i částečná shoda)."

    def add_arguments(self, parser):
        parser.add_argument("kod")
        parser.add_argument("--presne", action="store_true", help="Jen přesná shoda kódu.")

    def handle(self, *args, **options):
        kod = options["kod"]
        if options["presne"]:
            meters = Meter.objects.filter(code=kod)
        else:
            meters = Meter.objects.filter(code__icontains=kod)

        if not meters:
            self.stdout.write(self.style.WARNING(f"Žádné měřidlo neodpovídá '{kod}'."))
            return

        for meter in meters.select_related("site"):
            self.stdout.write(self.style.WARNING(f"\n=== měřidlo {meter.code} ({meter.site.name}, virtuální={meter.is_virtual}) ==="))
            keys = AllocationKey.objects.filter(meter=meter).select_related(
                "client_card__client", "service_item"
            )
            if not keys:
                self.stdout.write("  žádné klíče na tomto měřidle")
                continue
            for key in keys:
                self.stdout.write(
                    f"  {key.client_card.client.name} ({key.client_card}): "
                    f"položka={key.service_item.name!r} typ={key.allocation_type} hodnota={key.value}"
                )
