"""
Diagnostika: vypise vsechny klice (vsech klientu/karet) polozky
"uklidove sluzby spolecnych prostor NJ" s jejich vahou (hodnota klice),
aktivnimi dny v obdobi, efektivni vahou a vyslednym normalizovanym
podilem - stejnym zpusobem, jakym je pocita billing/engine.py
(_weighted_shares). Urceno k rucnimu dohledani chybne/chybejici/
duplicitni vahy proti referencnimu PDF.

Pouziti:
  python manage.py diag_uklid_nj_vahy --period=06/2026
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from billing.engine import ABSOLUTE_AMOUNT_TYPES
from core.models import Period, ServicePoolItem

ITEM_NAME = "úklidové služby společných prostor NJ"


class Command(BaseCommand):
    help = "Vypíše váhy/podíly všech klientů pro úklidové služby společných prostor NJ."

    def add_arguments(self, parser):
        parser.add_argument("--period", required=True, help="MM/RRRR, např. 06/2026")
        parser.add_argument("--item", default=ITEM_NAME)

    def handle(self, *args, **options):
        month_str, year_str = options["period"].split("/")
        period = Period.objects.filter(year=int(year_str), month=int(month_str)).first()
        if period is None:
            raise CommandError(f"Období {options['period']} nenalezeno.")

        item = ServicePoolItem.objects.filter(name=options["item"]).first()
        if item is None:
            raise CommandError(f"Položka {options['item']!r} nenalezena.")

        period_start, period_end = period.date_range()
        days_in_period = Decimal(period.days_in_period)

        all_keys = list(
            item.allocation_keys.select_related("client_card__client", "client_card__unit")
        )
        self.stdout.write(self.style.WARNING(f"=== {item} | období {period} ({days_in_period} dní) ==="))
        self.stdout.write(f"celkem klíčů na položce: {len(all_keys)}\n")

        raw_weights = {}
        rows = []
        for key in all_keys:
            card = key.client_card
            valid = key.is_valid_for_period(period)
            active_days = card.active_days_in_period(period_start, period_end) if valid else 0

            if key.allocation_type in ABSOLUTE_AMOUNT_TYPES:
                rows.append((card, key, "PEVNÁ/PLOCHA - mimo vážený podíl", None, active_days, valid))
                continue

            base = key.value or Decimal("0")
            effective_weight = base * (Decimal(active_days) / days_in_period) if active_days > 0 else Decimal("0")
            if active_days > 0:
                raw_weights[card.id] = raw_weights.get(card.id, Decimal("0")) + effective_weight
            rows.append((card, key, key.get_allocation_type_display(), effective_weight, active_days, valid))

        total = sum(raw_weights.values()) or Decimal("1")

        self.stdout.write(
            f"{'klient':40} {'karta':30} {'typ':28} {'váha':>10} {'akt.dny':>8} "
            f"{'eff.váha':>12} {'podíl':>10} {'billed':>7} {'valid':>6} {'karta akt.':>10}"
        )
        for card, key, type_label, effective_weight, active_days, valid in rows:
            share = (effective_weight / total) if effective_weight is not None else None
            share_str = f"{share*100:.3f}%" if share is not None else "-"
            eff_str = f"{effective_weight:.4f}" if effective_weight is not None else "-"
            self.stdout.write(
                f"{card.client.name[:40]:40} {str(card)[:30]:30} {type_label[:28]:28} "
                f"{str(key.value):>10} {active_days:>8} {eff_str:>12} {share_str:>10} "
                f"{str(key.is_billed):>7} {str(valid):>6} {str(card.is_active):>10}"
            )

        self.stdout.write(f"\nsoučet efektivních vah (jmenovatel normalizace) = {total}")
        self.stdout.write(f"počet karet s nenulovou vahou = {len(raw_weights)}")
