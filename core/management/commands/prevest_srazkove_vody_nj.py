"""
Prevede klice polozky "srazkove vody NJ" z Pevne castky na
Plocha x cena/m2 (stejny funkcni vzor jako "srazkove vody FM") a
zalozi/aktualizuje Cenik (PriceList) na 55 Kc/m2/rok pro 06/2026.

Puvodni pevne castky u 11 z 12 klientu presne odpovidaly 55 Kc/m2/rok
(hodnota*12/plocha == 55) - jen CALAMARI SE melo jinou efektivni sazbu
(61,11 Kc/m2), sjednoceno na 55 Kc/m2 jako ostatni (viz konverzace).

Vymera (AllocationKey.value) se pocita ZIVE z aktualnich CardUnit
klienta (area_m2_override nebo Unit.area_m2), ne z pevne zadanych
cisel - kdyby se mezitim plocha zmenila, pouzije se aktualni stav.

Pouziti:
  python manage.py prevest_srazkove_vody_nj
  python manage.py prevest_srazkove_vody_nj --dry-run
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.models import AllocationKey, Period, PriceList, ServicePoolItem

PRICE_PER_M2_ROK = Decimal("55")
PRICE_PERIOD = (2026, 6)


class Command(BaseCommand):
    help = "Převede srážkové vody NJ z Pevné částky na Plocha × cena/m² (55 Kč/m²/rok)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se změnilo")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        item = ServicePoolItem.objects.filter(
            name__icontains="srážkové vody", site__name__icontains="NJ"
        ).first()
        if item is None:
            self.stdout.write(self.style.ERROR("Položka 'srážkové vody NJ' nenalezena."))
            return

        year, month = PRICE_PERIOD
        period = Period.objects.filter(year=year, month=month).first()
        if period is None:
            self.stdout.write(self.style.ERROR(f"Období {month:02d}/{year} neexistuje."))
            return

        self.stdout.write(f"Ceník: {item} / {period} -> {PRICE_PER_M2_ROK} Kč/m²/rok")
        if not dry_run:
            PriceList.objects.update_or_create(
                service_item=item, period=period,
                defaults={"price_per_unit": PRICE_PER_M2_ROK, "note": "Sjednoceno na 55 Kč/m²/rok"},
            )

        keys = item.allocation_keys.select_related("client_card__client").filter(
            allocation_type=AllocationKey.AllocationType.FIXED_AMOUNT
        )
        converted = 0
        for key in keys:
            card = key.client_card
            total_area = sum(
                ((cu.area_m2_override if cu.area_m2_override is not None else cu.unit.area_m2) or Decimal("0"))
                for cu in card.card_units.select_related("unit").all()
            )
            if total_area <= 0:
                self.stdout.write(self.style.WARNING(
                    f"{card.client.name}: nulová/chybějící plocha - přeskočeno, klíč zůstává Pevná částka."
                ))
                continue

            old_value = key.value
            self.stdout.write(
                f"{card.client.name}: Pevná částka {old_value} Kč -> Plocha × cena/m², "
                f"plocha={total_area} m² (~{(total_area * PRICE_PER_M2_ROK / 12).quantize(Decimal('0.01'))} Kč/měsíc)"
            )
            converted += 1
            if not dry_run:
                key.allocation_type = AllocationKey.AllocationType.AREA_PRICE
                key.value = total_area
                key.save(update_fields=["allocation_type", "value"])

        prefix = "--dry-run: " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"\n{prefix}Převedeno klíčů: {converted}."))
