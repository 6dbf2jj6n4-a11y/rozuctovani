"""
Prevede existujici klice typu 'fixed_amount' u polozky srazkove vody na
novy typ 'area_price' (vymera x cena/m2 z Ceniku, dopocitava se dynamicky).

Puvodni hodnota klice (fixed_amount) = vymera * cena/m2/rok / 12. Aby
prevod nezmenil aktualne fakturovanou castku, vymera se dopocita zpetne
z existujici hodnoty a AKTUALNI ceny v Ceniku (musi tam tedy uz byt
zadana pred spustenim tohoto prikazu):
  vymera = puvodni_hodnota * 12 / cena_za_m2_rok

Pouziti:
  python manage.py prevod_srazky_area_price --site FM --dry-run
  python manage.py prevod_srazky_area_price --site FM
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from core.models import AllocationKey, PriceList, Period, ServicePoolItem, Site


class Command(BaseCommand):
    help = "Prevede fixed_amount klice srazkove vody na area_price (vymera x cena/m2 z Ceniku)."

    def add_arguments(self, parser):
        parser.add_argument("--site", type=str, required=True)
        parser.add_argument(
            "--item-name", type=str, default="srážkové vody",
            help="Podretezec nazvu polozky zasobniku (vychozi: 'srážkové vody').",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        site = Site.objects.filter(name__icontains=options["site"]).first()
        if not site:
            raise CommandError(f"Areál '{options['site']}' nenalezen.")

        service_item = ServicePoolItem.objects.filter(
            site=site, name__icontains=options["item_name"]
        ).first()
        if not service_item:
            raise CommandError(f"Položka obsahující '{options['item_name']}' nenalezena pro {site}.")

        # Aktualni cena podle nejnovejsiho obdobi, pro ktere existuje ceny zaznam.
        latest_period = Period.objects.order_by("-year", "-month").first()
        price = PriceList.get_price_for_period(service_item, latest_period) if latest_period else None
        if price is None:
            raise CommandError(
                f"Pro '{service_item}' není v Ceníku zadaná žádná cena - nejdřív ji zadej "
                f"(Kč/m²/rok), pak spusť tento příkaz znovu."
            )

        self.stdout.write(f"Položka: {service_item}, použitá cena: {price} Kč/m²/rok\n")

        keys = AllocationKey.objects.filter(
            service_item=service_item,
            allocation_type=AllocationKey.AllocationType.FIXED_AMOUNT,
        ).select_related("client_card")

        converted = 0
        skipped = 0
        for key in keys:
            if not key.value:
                self.stdout.write(f"  {key.client_card}: přeskočeno (prázdná hodnota)")
                skipped += 1
                continue
            area = (key.value * 12 / price).quantize(Decimal("0.01"))
            recomputed = (area * price / 12).quantize(Decimal("0.01"))
            self.stdout.write(
                f"  {key.client_card}: {key.value} Kč/měsíc -> {area} m² "
                f"(zpětný přepočet: {recomputed} Kč/měsíc)"
            )
            if not options["dry_run"]:
                key.allocation_type = AllocationKey.AllocationType.AREA_PRICE
                key.value = area
                key.save(update_fields=["allocation_type", "value"])
            converted += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n{'(dry-run, nic se neuložilo) ' if options['dry_run'] else ''}"
            f"Převedeno {converted} klíčů, {skipped} přeskočeno."
        ))
