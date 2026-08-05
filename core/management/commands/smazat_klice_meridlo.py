"""
Jednorazova oprava: smaze VSECHNY AllocationKey napojene na zadane
meridlo (podle kodu), napric vsemi kartami/klienty - viz konverzace
s Danielem (T_SPOL).

BEZ --provest jen VYPISE, co by smazal. S --provest smaze.

Pouziti:
  python manage.py smazat_klice_meridlo --meter-code=T_SPOL
  python manage.py smazat_klice_meridlo --meter-code=T_SPOL --provest
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import AllocationKey, Meter


class Command(BaseCommand):
    help = "Smaže všechny klíče (napříč kartami) napojené na zadané měřidlo."

    def add_arguments(self, parser):
        parser.add_argument("--meter-code", required=True)
        parser.add_argument("--provest", action="store_true", help="Skutečně smazat (jinak jen náhled).")

    def handle(self, *args, **options):
        meter = Meter.objects.filter(code__iexact=options["meter_code"]).first()
        if meter is None:
            raise CommandError(f'Měřidlo s kódem {options["meter_code"]!r} nenalezeno.')

        keys = AllocationKey.objects.filter(meter=meter).select_related(
            "client_card__client", "service_item"
        )
        if not keys:
            self.stdout.write(self.style.SUCCESS(f"Žádné klíče napojené na {meter} nenalezeny - nic k mazání."))
            return

        self.stdout.write(self.style.WARNING(f"Měřidlo: {meter}"))
        self.stdout.write(self.style.WARNING(f"Nalezeno {keys.count()} klíčů k smazání:"))
        for key in keys:
            self.stdout.write(
                f"  {key.client_card.client.name} ({key.client_card}) / {key.service_item.name}: "
                f"{key.get_allocation_type_display()} hodnota={key.value}"
            )

        if options["provest"]:
            count = keys.count()
            keys.delete()
            self.stdout.write(self.style.SUCCESS(f"\nSmazáno {count} klíčů."))
        else:
            self.stdout.write(self.style.WARNING("\nToto byl jen náhled. Pro smazání spusť s --provest."))
