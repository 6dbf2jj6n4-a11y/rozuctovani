"""
Porovná mailový kontakt (Client.contact_email) u našich Klientů s
evidencí "adresar" v ABRA Flexi - párování podle IČO (spolehlivější
než podle názvu, viz zkušenost s "Ing. Roman Chamrad" vs. "... SHIVA
SHOP" při porovnávání faktur).

Použití:
  python manage.py porovnat_emaily_flexi
  python manage.py porovnat_emaily_flexi --jen-nesedi
"""
from django.core.management.base import BaseCommand, CommandError

from core.flexi_client import FlexiAPIError, FlexiClient
from core.models import Client


def _clean_ico(value):
    return (value or "").strip().lstrip("0") or (value or "").strip()


class Command(BaseCommand):
    help = "Porovná e-mail u našich Klientů s adresářem ve Flexi (párováno podle IČO)."

    def add_arguments(self, parser):
        parser.add_argument("--jen-nesedi", action="store_true", help="Vypsat jen řádky, které nesedí")

    def handle(self, *args, **options):
        try:
            flexi_client = FlexiClient()
            records = flexi_client.list_records(
                "adresar",
                extra_params={"limit": 0, "detail": "full"},
            )
        except KeyError as e:
            raise CommandError(f"Chybí env proměnná {e} (FLEXI_URL, FLEXI_COMPANY, FLEXI_USER, FLEXI_PASS)")
        except FlexiAPIError as e:
            raise CommandError(f"Flexi API chyba {e.status_code}: {e.response_body}")

        self.stdout.write(f"Načteno {len(records)} záznamů adresáře z Flexi.\n")

        flexi_by_ico = {}
        for rec in records:
            ico = _clean_ico(rec.get("ic"))
            if not ico:
                continue
            flexi_by_ico[ico] = rec

        clients = Client.objects.exclude(ico="").order_by("name")

        header = f"{'Klient':<35}{'IČO':<12}{'Náš e-mail':<32}{'Flexi e-mail':<32}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        mismatches = 0
        not_found = 0
        for client in clients:
            ico = _clean_ico(client.ico)
            rec = flexi_by_ico.get(ico)
            our_email = (client.contact_email or "").strip()

            if rec is None:
                not_found += 1
                if not options["jen_nesedi"]:
                    continue
                self.stdout.write(self.style.WARNING(
                    f"{client.name[:33]:<35}{client.ico:<12}{our_email[:30]:<32}{'<- IČO nenalezeno ve Flexi':<32}"
                ))
                continue

            flexi_email = (rec.get("email") or "").strip()
            kontakty = rec.get("kontakty") or []

            same = our_email.lower() == flexi_email.lower()
            if same and options["jen_nesedi"]:
                continue

            flag = ""
            if not same:
                mismatches += 1
                flag = "<- NESEDÍ"
                if not flexi_email and kontakty:
                    flag += " (Flexi má vyplněné 'kontakty', ne pole 'email' - zkontroluj ručně)"

            row = f"{client.name[:33]:<35}{client.ico:<12}{our_email[:30]:<32}{flexi_email[:30] or '(prázdné)':<32}"
            if flag:
                self.stdout.write(self.style.WARNING(f"{row}  {flag}"))
            else:
                self.stdout.write(row)

        self.stdout.write("-" * len(header))
        self.stdout.write(f"\n{mismatches} klient(ů) má jiný e-mail než ve Flexi.")
        if not_found:
            self.stdout.write(f"{not_found} klient(ů) se nepodařilo dohledat ve Flexi podle IČO.")
