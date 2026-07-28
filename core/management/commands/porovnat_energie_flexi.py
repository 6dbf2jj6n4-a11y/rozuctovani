"""
Porovná vydané faktury z ABRA Flexi (popis "energie MM/YYYY") s naším
vyúčtováním (BillingLine) za stejné období - po klientech A třídách
(Elektřina/Voda/Teplo/Ostatní).

Srovnává se s částkou bez DPH (Flexi položky: sumZklCelkem) - naše
vyúčtování je bez DPH.

Kód položky ve Flexi (ELEKTRO/VODA/TEPLO/OSTATNI) se mapuje na
ServicePoolItem.InvoiceClass. Řádek "Zaokrouhleno" (bez kódu) se
přičítá k Ostatní, aby součty za fakturu seděly na korunu.

Použití:
  python manage.py porovnat_energie_flexi 06/2026
  python manage.py porovnat_energie_flexi 06/2026 --jen-nesedi
"""
import unicodedata
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from core.flexi_client import FlexiAPIError, FlexiClient
from core.models import BillingLine, Period, ServicePoolItem

KOD_TO_CLASS = {
    "ELEKTRO": ServicePoolItem.InvoiceClass.ELECTRICITY,
    "VODA": ServicePoolItem.InvoiceClass.WATER,
    "TEPLO": ServicePoolItem.InvoiceClass.HEAT,
    "OSTATNI": ServicePoolItem.InvoiceClass.OTHER,
    "OSTATNÍ": ServicePoolItem.InvoiceClass.OTHER,
    "": ServicePoolItem.InvoiceClass.OTHER,  # "Zaokrouhleno" - bez vlastniho kodu
}


def _normalize(name):
    decomposed = unicodedata.normalize("NFKD", name or "")
    without_diacritics = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in without_diacritics.lower() if c.isalnum())


def _num(value):
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return Decimal("0")


class Command(BaseCommand):
    help = 'Porovná faktury "energie MM/YYYY" z Flexi s naším vyúčtováním, po klientech a třídách.'

    def add_arguments(self, parser):
        parser.add_argument("period", type=str, help="MM/YYYY, např. 06/2026")
        parser.add_argument("--jen-nesedi", action="store_true", help="Vypsat jen řádky, které nesedí")

    def handle(self, *args, **options):
        try:
            month_str, year_str = options["period"].split("/")
            month, year = int(month_str), int(year_str)
        except ValueError:
            raise CommandError("Období zadej ve formátu MM/YYYY, např. 06/2026")

        period = Period.objects.filter(year=year, month=month).first()
        if not period:
            raise CommandError(f"Období {options['period']} v naší appce neexistuje.")

        popis = f"energie {month:02d}/{year}"

        try:
            flexi_client = FlexiClient()
            invoices = flexi_client.list_records(
                "faktura-vydana",
                filter_expr=f"popis = '{popis}'",
                extra_params={"limit": 0, "detail": "full"},
            )
        except KeyError as e:
            raise CommandError(f"Chybí env proměnná {e} (FLEXI_URL, FLEXI_COMPANY, FLEXI_USER, FLEXI_PASS)")
        except FlexiAPIError as e:
            raise CommandError(f"Flexi API chyba {e.status_code}: {e.response_body}")

        # {(normalizovany_klient, trida): Decimal}
        flexi_amounts = defaultdict(Decimal)
        flexi_names = {}
        unknown_kods = set()

        for inv in invoices:
            name = inv.get("nazFirmy") or (inv.get("firma@showAs") or "").split(":", 1)[-1].strip()
            key_client = _normalize(name)
            flexi_names[key_client] = name

            url = flexi_client._evidence_url(f"faktura-vydana/{inv['id']}/faktura-vydana-polozka")
            try:
                response = flexi_client._request("GET", url, params={"detail": "full"})
            except FlexiAPIError as e:
                self.stdout.write(self.style.WARNING(f"{name}: chyba načtení položek {e.status_code}"))
                continue

            items = (response or {}).get("winstrom", {}).get("faktura-vydana-polozka", [])
            for item in items:
                kod = (item.get("kod") or "").strip()
                invoice_class = KOD_TO_CLASS.get(kod)
                if invoice_class is None:
                    unknown_kods.add(kod)
                    invoice_class = ServicePoolItem.InvoiceClass.OTHER
                amount = item.get("sumZklCelkem")
                if amount is None:
                    amount = item.get("sumCelkem")
                flexi_amounts[(key_client, invoice_class)] += _num(amount)

        # nase vyuctovani - BillingLine.amount po klientech a tridach
        our_amounts = defaultdict(Decimal)
        our_names = {}
        lines = (
            BillingLine.objects.filter(period=period)
            .select_related("client_card__client", "service_item")
        )
        for line in lines:
            client = line.client_card.client
            key_client = _normalize(client.name)
            our_names[key_client] = client.name
            our_amounts[(key_client, line.service_item.invoice_class)] += line.amount

        class_labels = dict(ServicePoolItem.InvoiceClass.choices)
        all_client_keys = sorted(
            set(flexi_names) | set(our_names),
            key=lambda k: (our_names.get(k) or flexi_names.get(k)),
        )

        header = f"{'Klient':<32}{'Třída':<12}{'Naše (Kč)':>14}{'Flexi bez DPH':>16}{'Rozdíl':>12}"
        self.stdout.write(f"Porovnání energií za {period} (popis {popis!r}, {len(invoices)} faktur)\n")
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        total_our = total_flexi = Decimal("0")
        mismatches = 0
        for client_key in all_client_keys:
            name = our_names.get(client_key) or flexi_names.get(client_key)
            for class_key, class_label in class_labels.items():
                our_amount = our_amounts.get((client_key, class_key), Decimal("0"))
                flx_amount = flexi_amounts.get((client_key, class_key), Decimal("0"))
                if our_amount == 0 and flx_amount == 0:
                    continue
                diff = our_amount - flx_amount
                total_our += our_amount
                total_flexi += flx_amount

                flag = ""
                if our_amount == 0:
                    flag = "<- chybí v našem vyúčtování"
                elif flx_amount == 0:
                    flag = "<- chybí ve Flexi"
                elif abs(diff) > 2:
                    flag = "<- NESEDÍ"
                if flag:
                    mismatches += 1
                elif options["jen_nesedi"]:
                    continue

                row = f"{name[:30]:<32}{class_label:<12}{our_amount:>14,.2f}{flx_amount:>16,.2f}{diff:>12,.2f}"
                if flag:
                    self.stdout.write(self.style.WARNING(f"{row}  {flag}"))
                else:
                    self.stdout.write(row)

        self.stdout.write("-" * len(header))
        self.stdout.write(
            f"{'CELKEM':<32}{'':<12}{total_our:>14,.2f}{total_flexi:>16,.2f}{total_our - total_flexi:>12,.2f}"
        )

        if unknown_kods:
            self.stdout.write(self.style.WARNING(f"\nNeznámé kódy položek (napočítány jako Ostatní): {unknown_kods}"))

        if mismatches:
            self.stdout.write(self.style.WARNING(f"\n{mismatches} řádků (klient × třída) nesedí nebo chybí na jedné straně."))
        else:
            self.stdout.write(self.style.SUCCESS("\nVšechny částky sedí."))
