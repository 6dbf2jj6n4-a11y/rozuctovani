"""
Rychla diagnostika: ukaze presny aktualni stav v DB pro "hlavní odběr
elektro NJ" - ma polozka nastavene hlavni meridlo (item.meter), jaky maji
skutecne typ klice na konkretnich merenych kodech (E_AB1_10 apod.), a co
je ulozene v BillingLine.calc_detail pro dane obdobi/klienta. Cilem je
zjistit, proc podil po opravach v enginu porad vychazi stejne (0,025 %).

Pouziti:
  python manage.py diag_elektro_nj_stav --period=06/2026 --item="hlavní odběr elektro NJ" --client="Aktiv Novostav"
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from core.models import BillingLine, Client, Period, ServicePoolItem


class Command(BaseCommand):
    help = "Ukáže stav item.meter, typy klíčů a calc_detail pro danou položku/klienta/období."

    def add_arguments(self, parser):
        parser.add_argument("--period", required=True)
        parser.add_argument("--item", required=True)
        parser.add_argument("--client", required=True)

    def handle(self, *args, **options):
        month_str, year_str = options["period"].split("/")
        period = Period.objects.filter(year=int(year_str), month=int(month_str)).first()
        if period is None:
            raise CommandError(f"Období {options['period']} nenalezeno.")

        item = ServicePoolItem.objects.select_related("meter", "site").filter(name=options["item"]).first()
        if item is None:
            raise CommandError(f"Položka {options['item']!r} nenalezena.")

        client = Client.objects.filter(name__icontains=options["client"]).first()
        if client is None:
            raise CommandError(f"Klient {options['client']!r} nenalezen.")

        self.stdout.write(self.style.WARNING(f"=== {item} ({item.site.name}) ==="))
        self.stdout.write(f"item.meter = {item.meter!r}  (pokud None, polozka NENI merena na urovni polozky!)")
        self.stdout.write(f"item.default_amount_czk = {item.default_amount_czk}")

        self.stdout.write(self.style.WARNING("\n-- VŠECHNY klíče této položky (aktuální stav v DB) --"))
        for key in item.allocation_keys.select_related("client_card__client", "meter").order_by("client_card__client__name"):
            self.stdout.write(
                f"  {key.client_card.client.name} ({key.client_card}): "
                f"typ={key.allocation_type!r} ({key.get_allocation_type_display()}) "
                f"hodnota={key.value} meridlo={key.meter} "
                f"platnost={key.valid_from}–{key.valid_to or '∞'} karta_aktivni={key.client_card.is_active}"
            )

        self.stdout.write(self.style.WARNING(f"\n-- BillingLine.calc_detail pro {client.name}, {item}, {period} --"))
        lines = BillingLine.objects.filter(period=period, client_card__client=client, service_item=item)
        if not lines:
            self.stdout.write(self.style.ERROR("  Žádný BillingLine nenalezen."))
        for line in lines:
            self.stdout.write(
                f"  card={line.client_card} amount={line.amount} share={line.share} "
                f"calc_detail={line.calc_detail}"
            )
