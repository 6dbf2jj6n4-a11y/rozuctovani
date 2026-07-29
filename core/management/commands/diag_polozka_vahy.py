"""
Obecna diagnostika: vypise vahy/jednotky/podily VSECH klicu jedne polozky
zasobniku pro dane obdobi - funguje jak pro merene polozky (hlavni meridlo
+ podruzna meridla + vazeny zbytek), tak pro ciste vazene polozky (OSTATNÍ
bez meridla). Pouziva presne stejne funkce jako skutecny vypocet
(billing/engine.py _consumption_shares/_weighted_shares), takze vysledek
je vzdy konzistentni se skutecnym vyuctovanim.

Pouziti:
  python manage.py diag_polozka_vahy --period=06/2026 --item="hlavní odběr voda NJ"
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from billing.engine import ABSOLUTE_AMOUNT_TYPES, _consumption_shares, _weighted_shares
from core.models import AllocationKey, Period, ServicePoolItem


class Command(BaseCommand):
    help = "Vypíše váhy/jednotky/podíly všech klíčů dané položky zásobníku pro dané období."

    def add_arguments(self, parser):
        parser.add_argument("--period", required=True, help="MM/RRRR, např. 06/2026")
        parser.add_argument("--item", required=True)

    def handle(self, *args, **options):
        month_str, year_str = options["period"].split("/")
        period = Period.objects.filter(year=int(year_str), month=int(month_str)).first()
        if period is None:
            raise CommandError(f"Období {options['period']} nenalezeno.")

        item = ServicePoolItem.objects.filter(name=options["item"]).first()
        if item is None:
            candidates = ServicePoolItem.objects.filter(name__icontains=options["item"].split()[0])
            names = ", ".join(f"{c.id}:{c.name!r}" for c in candidates) or "(nic podobného)"
            raise CommandError(f"Položka {options['item']!r} nenalezena. Podobné: {names}")

        warnings = []
        prev_period = period.previous_period()

        self.stdout.write(self.style.WARNING(f"=== {item} | období {period} ==="))
        self.stdout.write(f"měřidlo na položce: {item.meter or '(žádné - čistě vážená položka)'}\n")

        all_keys = list(
            item.allocation_keys.select_related("client_card__client", "client_card__unit", "meter")
        )
        valid_keys = [k for k in all_keys if k.is_valid_for_period(period)]
        invalid_keys = [k for k in all_keys if k not in valid_keys]

        if item.meter:
            total_consumption = item.meter.consumption_for(period)
            current = item.meter.readings.filter(period=period).first()
            previous = item.meter.readings.filter(period=prev_period).first() if prev_period else None
            self.stdout.write(
                f"hlavní měřidlo {item.meter}: předchozí={previous.value if previous else '—'} "
                f"aktuální={current.value if current else '—'} spotřeba={total_consumption}"
            )

            by_key_share = {}
            shares, total_consumption = _consumption_shares(item, period, warnings, by_key_out=by_key_share)

            submeter_keys = [k for k in valid_keys if k.allocation_type == AllocationKey.AllocationType.SUBMETER]
            weight_keys = [
                k for k in valid_keys
                if k.allocation_type not in (AllocationKey.AllocationType.SUBMETER,) and k.allocation_type not in ABSOLUTE_AMOUNT_TYPES
            ]

            self.stdout.write(f"\n-- podružná měřidla (1:1, spotřeba/celková spotřeba) --")
            sum_sub = Decimal("0")
            for key in submeter_keys:
                sub_current = key.meter.readings.filter(period=period).first() if key.meter else None
                sub_previous = key.meter.readings.filter(period=prev_period).first() if key.meter and prev_period else None
                sub_consumption = key.meter.consumption_for(period) if key.meter else None
                if sub_consumption:
                    sum_sub += sub_consumption
                share = by_key_share.get(key.id)
                share_str = f"{share*100:.3f}%" if share is not None else "-"
                self.stdout.write(
                    f"  {key.client_card.client.name} ({key.client_card}): měřidlo={key.meter} "
                    f"předchozí={sub_previous.value if sub_previous else '—'} "
                    f"aktuální={sub_current.value if sub_current else '—'} "
                    f"spotřeba={sub_consumption} podíl={share_str}"
                )

            residual = (total_consumption - sum_sub) if total_consumption is not None else None
            residual_fraction = (residual / total_consumption) if (total_consumption and residual is not None) else None
            self.stdout.write(f"\nzbytková (společná) spotřeba = {residual}  (residual_fraction={residual_fraction})")

            days_in_period = Decimal(period.days_in_period)
            self.stdout.write(f"\n-- vážené klíče na zbytkové spotřebě --")
            for key in weight_keys:
                active_days = key.client_card.active_days_in_period(*period.date_range())
                base = key.value or Decimal("0")
                eff = base * (Decimal(active_days) / days_in_period) if active_days > 0 else Decimal("0")
                share = by_key_share.get(key.id)
                share_str = f"{share*100:.3f}%" if share is not None else "-"
                self.stdout.write(
                    f"  {key.client_card.client.name} ({key.client_card}): {key.get_allocation_type_display()} "
                    f"hodnota={key.value} akt.dny={active_days} eff.váha={eff:.4f} "
                    f"podíl_z_celku={share_str} aktivní_karta={key.client_card.is_active}"
                )
        else:
            weight_keys = [k for k in valid_keys if k.allocation_type not in ABSOLUTE_AMOUNT_TYPES]
            by_key_share = {}
            _weighted_shares(weight_keys, period, by_key_out=by_key_share)
            days_in_period = Decimal(period.days_in_period)

            self.stdout.write(f"-- vážené klíče --")
            for key in weight_keys:
                active_days = key.client_card.active_days_in_period(*period.date_range())
                base = key.value or Decimal("0")
                eff = base * (Decimal(active_days) / days_in_period) if active_days > 0 else Decimal("0")
                share = by_key_share.get(key.id)
                share_str = f"{share*100:.3f}%" if share is not None else "-"
                self.stdout.write(
                    f"  {key.client_card.client.name} ({key.client_card}): {key.get_allocation_type_display()} "
                    f"hodnota={key.value} akt.dny={active_days} eff.váha={eff:.4f} "
                    f"podíl={share_str} aktivní_karta={key.client_card.is_active}"
                )

        if invalid_keys:
            self.stdout.write(self.style.WARNING(f"\n-- klíče VYNECHANÉ z výpočtu (neplatné období nebo neaktivní karta) --"))
            for key in invalid_keys:
                self.stdout.write(
                    f"  {key.client_card.client.name} ({key.client_card}): {key.get_allocation_type_display()} "
                    f"hodnota={key.value} aktivní_karta={key.client_card.is_active} "
                    f"platnost={key.valid_from}–{key.valid_to or '∞'}"
                )

        if warnings:
            self.stdout.write(self.style.ERROR("\n-- warnings --"))
            for w in warnings:
                self.stdout.write(f"  - {w}")
