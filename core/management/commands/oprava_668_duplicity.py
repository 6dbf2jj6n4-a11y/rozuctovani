"""
Jednorazova oprava: smaze 4 chybne vytvorene AllocationKey radky pro
Artalo design a LogicVision na meridlech 668NT/668VT, ktere omylem
skoncily pod polozkou "hlavní odběr elektro FM" (mely zustat jen pod
"odběr EAN 668 FM", kde uz spravne existuji jako weighted_count).
Zpusobil to prilis siroky fallback v import_klice_elektro.py (opraveno
samostatne), spustene pri diag_668_kontrola.

BEZ --dry-run jen VYPISE, co by smazal. S --provest smaze.

Pouziti:
  python manage.py oprava_668_duplicity            # jen nahled
  python manage.py oprava_668_duplicity --provest   # skutecne smaze
"""
from django.core.management.base import BaseCommand

from core.models import AllocationKey, Meter, Site


class Command(BaseCommand):
    help = "Smaže chybně vzniklé duplicitní klíče na 668NT/668VT pod 'hlavní odběr elektro FM'."

    def add_arguments(self, parser):
        parser.add_argument("--provest", action="store_true", help="Skutečně smazat (jinak jen náhled).")

    def handle(self, *args, **options):
        site = Site.objects.filter(name__icontains="FM").first()
        if not site:
            self.stdout.write(self.style.ERROR("Areál FM nenalezen."))
            return

        meters = Meter.objects.filter(site=site, code__in=["668NT", "668VT"])
        bad_keys = AllocationKey.objects.filter(
            meter__in=meters,
        ).exclude(service_item__name="odběr EAN 668 FM").select_related(
            "client_card__client", "service_item", "meter"
        )

        if not bad_keys:
            self.stdout.write(self.style.SUCCESS("Žádné chybné klíče nenalezeny - nic k opravě."))
            return

        self.stdout.write(self.style.WARNING(f"Nalezeno {bad_keys.count()} chybných klíčů:"))
        for key in bad_keys:
            self.stdout.write(
                f"  #{key.id}: {key.client_card.client.name} / položka={key.service_item.name!r} "
                f"měřidlo={key.meter.code} typ={key.allocation_type} hodnota={key.value}"
            )

        if options["provest"]:
            count = bad_keys.count()
            bad_keys.delete()
            self.stdout.write(self.style.SUCCESS(f"\nSmazáno {count} klíčů."))
        else:
            self.stdout.write(self.style.WARNING("\nToto byl jen náhled. Pro smazání spusť s --provest."))
