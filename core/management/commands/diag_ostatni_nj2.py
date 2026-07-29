"""
Diagnostika v2: presne zopakuje logiku billing/engine.py (vcetne
Plocha x cena/m2 klicu, ktere predchozi diag_ostatni_nj.py nepocital
do odectu z poolu) pro "odvoz komunalniho odpadu NJ" a "uklidove
sluzby spolecnych prostor NJ", a k tomu vypise ulozeny calc_detail
BillingLine radku Aktiv Novostav pro dane obdobi.

Pouziti:
  python manage.py diag_ostatni_nj2 --period=06/2026 --client="Aktiv Novostav"
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from billing.engine import ABSOLUTE_AMOUNT_TYPES, _fixed_amount_for, _weighted_shares
from core.models import BillingLine, Client, CostEntry, Period, ServicePoolItem


ITEM_NAMES = ["odvoz komunálního odpadu NJ", "úklidové služby společných prostor NJ"]


class Command(BaseCommand):
    help = "Přesně zopakuje engine.py logiku (vč. Plocha×cena/m²) pro vybrané OSTATNÍ položky NJ."

    def add_arguments(self, parser):
        parser.add_argument("--period", required=True, help="MM/RRRR, např. 06/2026")
        parser.add_argument("--client", default="Aktiv Novostav")

    def handle(self, *args, **options):
        month_str, year_str = options["period"].split("/")
        period = Period.objects.filter(year=int(year_str), month=int(month_str)).first()
        if period is None:
            raise CommandError(f"Období {options['period']} nenalezeno.")

        client = Client.objects.filter(name=options["client"]).first()
        if client is None:
            raise CommandError(f"Klient {options['client']!r} nenalezen.")

        period_start, period_end = period.date_range()
        warnings = []

        for name in ITEM_NAMES:
            item = ServicePoolItem.objects.filter(name=name).first()
            if item is None:
                self.stdout.write(self.style.ERROR(f'Položka "{name}" nenalezena.'))
                continue

            self.stdout.write(self.style.WARNING(f"\n=== {item} ==="))

            cost_entry = CostEntry.objects.filter(service_item=item, period=period).first()
            total_cost = cost_entry.get_amount_czk(period) if cost_entry else item.default_amount_czk
            self.stdout.write(f"total_cost = {total_cost}  (CostEntry={'ano' if cost_entry else 'NE - default_amount_czk'})")

            all_keys = list(item.allocation_keys.select_related("client_card__client"))
            valid_keys = [k for k in all_keys if k.is_valid_for_period(period)]
            fixed_keys = [k for k in valid_keys if k.allocation_type in ABSOLUTE_AMOUNT_TYPES]

            remaining_cost = total_cost
            self.stdout.write(f"\n-- pevné/plošné klíče (ABSOLUTE_AMOUNT_TYPES) --")
            for key in fixed_keys:
                active_days = key.client_card.active_days_in_period(period_start, period_end)
                if active_days <= 0:
                    self.stdout.write(f"  {key.client_card.client.name}: NEAKTIVNÍ v období, přeskočeno")
                    continue
                amount = _fixed_amount_for(key, item, period, warnings)
                deducted = ""
                if amount is not None and key.deduct_from_pool:
                    remaining_cost -= amount
                    deducted = f"  <-- ODEČTENO Z POOLU (zbývá {remaining_cost})"
                self.stdout.write(
                    f"  {key.client_card.client.name}: {key.get_allocation_type_display()} "
                    f"hodnota={key.value} spočtená_částka={amount} "
                    f"odečíst_z_poolu={key.deduct_from_pool}{deducted}"
                )

            if remaining_cost is not None and remaining_cost < 0:
                self.stdout.write(self.style.ERROR(
                    f"  !!! remaining_cost by šel do záporu ({remaining_cost}) - "
                    f"engine.py by ho OŘÍZL NA 0 !!!"
                ))
                remaining_cost = Decimal("0")

            self.stdout.write(f"\nremaining_cost (po odečtech) = {remaining_cost}")

            weight_keys = [k for k in valid_keys if k.allocation_type not in ABSOLUTE_AMOUNT_TYPES]
            by_key_share = {}
            shares = _weighted_shares(weight_keys, period, by_key_out=by_key_share)
            self.stdout.write(f"\n-- vážené klíče (share = podíl na remaining_cost) --")
            for key in weight_keys:
                share = shares.get(key.client_card_id)
                amount = (remaining_cost * share) if (share is not None and remaining_cost is not None) else None
                marker = "  <-- AKTIV NOVOSTAV" if key.client_card.client_id == client.id else ""
                self.stdout.write(
                    f"  {key.client_card.client.name}: {key.get_allocation_type_display()} "
                    f"hodnota={key.value} share={share} spočtená_částka={amount}{marker}"
                )

            self.stdout.write(f"\n-- uložený BillingLine.calc_detail pro {client.name} --")
            lines = BillingLine.objects.filter(
                period=period, client_card__client=client, service_item=item
            )
            if not lines:
                self.stdout.write(self.style.ERROR("  ŽÁDNÝ BillingLine nenalezen pro tuto kartu/období/položku!"))
            for line in lines:
                self.stdout.write(
                    f"  card={line.client_card}  amount={line.amount}  share={line.share}  "
                    f"calc_detail={line.calc_detail}"
                )

        if warnings:
            self.stdout.write(self.style.WARNING("\n\n== warnings (stejné jako by je vygeneroval reálný přepočet) =="))
            for w in warnings:
                self.stdout.write(f"  - {w}")
