"""
Porovná vydané faktury z ABRA Flexi (popis 'nájem MM/YYYY') s naším
nájemným za stejné období. Nájemné neprochází přes billing/engine.py
(BillingLine) - nerozpočítává se mezi klienty, každá karta platí jen
podle vlastní plochy × sazby (CardUnit) - proto se tady počítá přímo
z aktivních karet klienta v daném období, s poměrnou částí podle počtu
aktivních dnů (viz ClientCard.active_days_in_period), stejně jako to
dělá billing/engine.py u ostatních položek.

Srovnává se s částkou bez DPH (sumZklCelkem) - naše nájemné je bez
DPH, ta se podle smlouvy připočítává až na faktuře.

Použití:
  python manage.py porovnat_najem_flexi 06/2026
"""
import unicodedata
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from core.flexi_client import FlexiAPIError, FlexiClient
from core.models import ClientCard, Period


def _normalize(name):
    """Klíč pro spárování klienta mezi naším systémem a Flexi. Oba systémy
    zapisují název firmy jinak formátovaný ("s.r.o." vs "s. r. o.",
    "Firma, a.s." vs "FIRMA a.s", chybějící "&" apod.) - proto se
    porovnává jen podle písmen a číslic, bez mezer/interpunkce/diakritiky.
    Genuinně odlišné názvy (např. doplněk obchodního jména) se tím
    záměrně nespárují - to už vyžaduje ruční kontrolu."""
    decomposed = unicodedata.normalize("NFKD", name or "")
    without_diacritics = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in without_diacritics.lower() if c.isalnum())


def _card_rent_for_period(card, period):
    """Nájemné karty za dané období, poměrné podle počtu aktivních dnů."""
    period_start, period_end = period.date_range()
    active_days = card.active_days_in_period(period_start, period_end)
    if active_days <= 0:
        return Decimal("0")
    monthly_total = sum(
        (cu.monthly_rent or Decimal("0") for cu in card.card_units.all()),
        Decimal("0"),
    )
    if active_days >= period.days_in_period:
        return monthly_total
    return monthly_total * Decimal(active_days) / Decimal(period.days_in_period)


class Command(BaseCommand):
    help = "Porovná faktury 'nájem MM/YYYY' z Flexi s naším vyúčtováním nájemného za stejné období."

    def add_arguments(self, parser):
        parser.add_argument("period", type=str, help="MM/YYYY, např. 06/2026")

    def handle(self, *args, **options):
        try:
            month_str, year_str = options["period"].split("/")
            month, year = int(month_str), int(year_str)
        except ValueError:
            raise CommandError("Období zadej ve formátu MM/YYYY, např. 06/2026")

        period = Period.objects.filter(year=year, month=month).first()
        if not period:
            raise CommandError(f"Období {options['period']} v naší appce neexistuje.")

        popis = f"nájem {month:02d}/{year}"

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

        flexi_by_client = {}
        for inv in invoices:
            name = inv.get("nazFirmy") or (inv.get("firma@showAs") or "").split(":", 1)[-1].strip()
            key = _normalize(name)
            entry = flexi_by_client.setdefault(key, {"name": name, "bez_dph": 0.0, "vc_dph": 0.0, "count": 0})
            entry["bez_dph"] += float(inv.get("sumZklCelkem") or 0)
            entry["vc_dph"] += float(inv.get("sumCelkem") or 0)
            entry["count"] += 1

        cards = ClientCard.objects.select_related("client").prefetch_related("card_units")
        our_by_client = {}
        for card in cards:
            rent = _card_rent_for_period(card, period)
            if rent == 0:
                continue
            key = _normalize(card.client.name)
            entry = our_by_client.setdefault(key, {"name": card.client.name, "amount": 0.0})
            entry["amount"] += float(rent)

        all_keys = sorted(
            set(flexi_by_client) | set(our_by_client),
            key=lambda k: (our_by_client.get(k) or flexi_by_client.get(k))["name"],
        )

        self.stdout.write(f"Srovnání nájemného za {period} - Flexi (popis '{popis}', {len(invoices)} faktur) vs. vyúčtování\n")
        self.stdout.write(
            f"{'Klient':<40}{'Naše (Kč)':>14}{'Flexi bez DPH':>16}{'Flexi vč. DPH':>16}{'Rozdíl':>14}"
        )
        self.stdout.write("-" * 100)

        total_our = total_flexi = 0.0
        mismatches = 0
        for key in all_keys:
            our = our_by_client.get(key)
            flx = flexi_by_client.get(key)
            our_amount = our["amount"] if our else 0.0
            flx_bez_dph = flx["bez_dph"] if flx else 0.0
            flx_vc_dph = flx["vc_dph"] if flx else 0.0
            name = (our or flx)["name"]
            diff = our_amount - flx_bez_dph
            total_our += our_amount
            total_flexi += flx_bez_dph

            flag = ""
            if our is None:
                flag = "<- chybí v našem vyúčtování"
            elif flx is None:
                flag = "<- chybí ve Flexi"
            elif abs(diff) > 2:
                flag = "<- NESEDÍ"
            if flag:
                mismatches += 1

            row = f"{name[:38]:<40}{our_amount:>14,.2f}{flx_bez_dph:>16,.2f}{flx_vc_dph:>16,.2f}{diff:>14,.2f}"
            if flag:
                self.stdout.write(self.style.WARNING(f"{row}  {flag}"))
            else:
                self.stdout.write(row)

        self.stdout.write("-" * 100)
        self.stdout.write(
            f"{'CELKEM':<40}{total_our:>14,.2f}{total_flexi:>16,.2f}{'':>16}{total_our - total_flexi:>14,.2f}"
        )

        if mismatches:
            self.stdout.write(self.style.WARNING(f"\n{mismatches} klient(ů) nesedí nebo chybí na jedné straně."))
        else:
            self.stdout.write(self.style.SUCCESS("\nVšechny částky sedí."))
