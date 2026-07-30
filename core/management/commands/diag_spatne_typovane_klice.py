"""
Diagnostika (jen cteni): najde klice typu "Podle váhy" (weighted_count),
ktere maji napojene REALNE meridlo (s vlastnimi odecty) - podle stejneho
pravidla, jake uz pouzivaji import_klice_*.py skripty (meter.readings.exists()).
Takove klice by mely byt typu "Podružné měřidlo" (submeter), aby se
pocitaly ze skutecne spotreby, ne z rucne zadane vahy.

Virtualni meridla (napr. E_SPOL, is_virtual=True, bez vlastnich odectu -
spotreba se dopocitava ze vzorce) se spravne NEPOCITAJI - ty maji zustat
weighted_count.

Pouziti:
  python manage.py diag_spatne_typovane_klice
  python manage.py diag_spatne_typovane_klice --site NJ
"""
from django.core.management.base import BaseCommand

from core.models import AllocationKey


class Command(BaseCommand):
    help = "Najde klíče 'Podle váhy' s napojeným reálným (neVirtuálním) měřidlem, které mají odečty."

    def add_arguments(self, parser):
        parser.add_argument("--site", default=None)

    def handle(self, *args, **options):
        qs = (
            AllocationKey.objects.filter(allocation_type="weighted_count", meter__isnull=False)
            .select_related("client_card__client", "service_item__site", "meter")
        )
        if options["site"]:
            qs = qs.filter(service_item__site__name__icontains=options["site"])

        mismatches = []
        for key in qs:
            meter = key.meter
            if meter.is_virtual:
                continue
            if meter.readings.exists():
                mismatches.append(key)

        self.stdout.write(self.style.WARNING(
            f"Zkontrolováno {qs.count()} klíčů 'Podle váhy' s měřidlem, "
            f"z toho {len(mismatches)} má reálné odečty (mělo by být 'Podružné měřidlo'):\n"
        ))
        by_site = {}
        for key in mismatches:
            site = key.service_item.site.name
            by_site.setdefault(site, []).append(key)

        for site, keys in sorted(by_site.items()):
            self.stdout.write(self.style.ERROR(f"[{site}] {len(keys)} klíčů:"))
            for key in keys:
                self.stdout.write(
                    f"  {key.client_card.client.name} / {key.service_item.name} / "
                    f"měřidlo={key.meter.code or key.meter.name} hodnota={key.value}"
                )
