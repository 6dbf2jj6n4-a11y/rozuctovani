"""
Vytáhne z ABRA Flexi vydané faktury, jejichž popis obsahuje zadaný text
(např. "energie 06/2026"), a vypíše jejich položky do přehledné tabulky -
podklad pro ruční porovnání se skutečným vyúčtováním v naší appce.

Flexi REST API nemá jednotny nazev pole pro polozky napric verzemi/
nastavenim - tenhle prikaz je proto DIAGNOSTICKY: pro prvni nalezenou
fakturu vypise VSECHNY klice v jejim JSON, at zjistime presny nazev pole
s polozkami, nez to natvrdo naformatujeme do tabulky.

Použití:
  python manage.py vytahnout_faktury_energie "energie 06/2026"
"""
import json

from django.core.management.base import BaseCommand, CommandError

from core.flexi_client import FlexiAPIError, FlexiClient


class Command(BaseCommand):
    help = "Vytáhne z Flexi faktury podle textu v popisu a vypíše jejich strukturu/položky."

    def add_arguments(self, parser):
        parser.add_argument("popis", type=str, help="Text hledaný v popisu faktury, např. 'energie 06/2026'")

    def handle(self, *args, **options):
        popis = options["popis"]

        try:
            flexi_client = FlexiClient()
            invoices = flexi_client.list_records(
                "faktura-vydana",
                filter_expr=f"popis like '%{popis}%'",
                extra_params={"limit": 0, "detail": "full"},
            )
        except KeyError as e:
            raise CommandError(f"Chybí env proměnná {e} (FLEXI_URL, FLEXI_COMPANY, FLEXI_USER, FLEXI_PASS)")
        except FlexiAPIError as e:
            raise CommandError(f"Flexi API chyba {e.status_code}: {e.response_body}")

        self.stdout.write(f"Nalezeno {len(invoices)} faktur s popisem obsahujícím {popis!r}.\n")

        if not invoices:
            return

        first = invoices[0]
        self.stdout.write(self.style.WARNING("--- Klíče první faktury (diagnostika) ---"))
        for key in sorted(first.keys()):
            value = first[key]
            preview = json.dumps(value, ensure_ascii=False)[:120] if not isinstance(value, str) else value[:120]
            self.stdout.write(f"  {key}: {preview}")

        self.stdout.write(self.style.WARNING("\n--- Základní přehled všech nalezených faktur ---"))
        for inv in invoices:
            name = inv.get("nazFirmy") or (inv.get("firma@showAs") or "").split(":", 1)[-1].strip()
            self.stdout.write(
                f"#{inv.get('id')} {name} - popis: {inv.get('popis')!r} - "
                f"bez DPH: {inv.get('sumZklCelkem')} - vč. DPH: {inv.get('sumCelkem')}"
            )
