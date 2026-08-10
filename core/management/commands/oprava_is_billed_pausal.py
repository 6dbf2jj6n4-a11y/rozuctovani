"""
Jednorazova oprava: CALAMARI SE (pronajimatel) a INNEXUM GROUP maji vsechny
sluzby zahrnute v jedne castce spolu s najmem (Daniel potvrdil 2026-08-12) -
nastavi is_billed=False na vsech jejich klicich KROME typu "Pevná částka"
(fixed_amount), ktery predstavuje samostatne fakturovanou polozku (napr.
"připojení k internetu NONSTOP" u INNEXUM GROUP).

Nemeni samotny vypocet podilu (is_billed neovlivnuje jmenovatel v enginu),
jen popisek "(v paušálu)" na klientskem vypisu.

BEZ --provest jen VYPISE, co by zmenil. S --provest ulozi.

Pouziti:
  python manage.py oprava_is_billed_pausal            # jen nahled
  python manage.py oprava_is_billed_pausal --provest   # skutecne ulozi
"""
from django.core.management.base import BaseCommand

from core.models import AllocationKey, Client

CLIENT_NAMES = ["CALAMARI SE", "INNEXUM GROUP"]


class Command(BaseCommand):
    help = 'Nastaví is_billed=False (kromě fixed_amount) u klíčů CALAMARI SE a INNEXUM GROUP.'

    def add_arguments(self, parser):
        parser.add_argument("--provest", action="store_true", help="Skutečně uložit (jinak jen náhled).")

    def handle(self, *args, **options):
        to_fix = []

        for name in CLIENT_NAMES:
            client = Client.objects.filter(name__icontains=name).first()
            if client is None:
                self.stdout.write(self.style.ERROR(f'Klient "{name}" nenalezen.'))
                continue

            keys = (
                AllocationKey.objects.filter(client_card__client=client, is_billed=True)
                .exclude(allocation_type=AllocationKey.AllocationType.FIXED_AMOUNT)
                .select_related("service_item", "client_card")
            )
            for key in keys:
                to_fix.append((client, key))

        if not to_fix:
            self.stdout.write(self.style.SUCCESS("Žádné klíče k opravě - nic k opravě."))
            return

        self.stdout.write(self.style.WARNING(f"Nalezeno {len(to_fix)} klíčů k opravě:"))
        for client, key in to_fix:
            self.stdout.write(f"  {client.name}: {key.service_item.name} (typ={key.allocation_type})")

        if options["provest"]:
            for _, key in to_fix:
                key.is_billed = False
                key.save(update_fields=["is_billed"])
            self.stdout.write(self.style.SUCCESS(f"\nUpraveno {len(to_fix)} klíčů."))
        else:
            self.stdout.write(self.style.WARNING("\nToto byl jen náhled. Pro uložení spusť s --provest."))
