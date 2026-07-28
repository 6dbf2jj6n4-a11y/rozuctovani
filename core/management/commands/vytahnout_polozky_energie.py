"""
Vytáhne z ABRA Flexi vydané faktury s popisem "energie MM/YYYY" včetně
jejich položek (evidence "faktura-vydana-polozka") a vypíše je do jedné
přehledné tabulky - podklad pro ruční porovnání se skutečným
vyúčtováním v naší appce (Vyúčtování → Detail).

Použití:
  python manage.py vytahnout_polozky_energie 06/2026
  python manage.py vytahnout_polozky_energie 06/2026 --csv vystup.csv
"""
import csv as csv_module

from django.core.management.base import BaseCommand, CommandError

from core.flexi_client import FlexiAPIError, FlexiClient


class Command(BaseCommand):
    help = 'Vytáhne z Flexi faktury "energie MM/YYYY" a jejich položky do přehledné tabulky.'

    def add_arguments(self, parser):
        parser.add_argument("period", type=str, help="MM/YYYY, např. 06/2026")
        parser.add_argument("--csv", type=str, default=None, help="Volitelně uložit i jako CSV soubor")

    def handle(self, *args, **options):
        try:
            month_str, year_str = options["period"].split("/")
            month, year = int(month_str), int(year_str)
        except ValueError:
            raise CommandError("Období zadej ve formátu MM/YYYY, např. 06/2026")

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

        self.stdout.write(f"Nalezeno {len(invoices)} faktur s popisem {popis!r}.\n")

        rows = []
        for inv in invoices:
            name = inv.get("nazFirmy") or (inv.get("firma@showAs") or "").split(":", 1)[-1].strip()
            invoice_id = inv["id"]

            url = flexi_client._evidence_url(
                f"faktura-vydana/{invoice_id}/faktura-vydana-polozka", suffix=""
            )
            try:
                response = flexi_client._request("GET", url, params={"detail": "full"})
            except FlexiAPIError as e:
                self.stdout.write(self.style.WARNING(f"{name} (#{invoice_id}): chyba načtení položek {e.status_code}"))
                continue

            items = (response or {}).get("winstrom", {}).get("faktura-vydana-polozka", [])
            for item in items:
                rows.append({
                    "klient": name,
                    "faktura": inv.get("kod"),
                    "kod_polozky": item.get("kod") or "",
                    "nazev_polozky": item.get("nazev") or "",
                    "mnozstvi": item.get("mnozMj"),
                    "cena_mj": item.get("cenaMj"),
                    "celkem_bez_dph": item.get("sumZklCelkem") if item.get("sumZklCelkem") is not None else item.get("sumCelkem"),
                    "celkem_s_dph": item.get("sumCelkem"),
                })

        self.stdout.write(
            f"{'Klient':<32}{'Faktura':<12}{'Kód pol.':<12}{'Název položky':<45}{'Množ.':>8}{'Kč bez DPH':>14}{'Kč s DPH':>12}"
        )
        self.stdout.write("-" * 135)
        for r in rows:
            self.stdout.write(
                f"{r['klient'][:30]:<32}{(r['faktura'] or ''):<12}{r['kod_polozky'][:10]:<12}"
                f"{r['nazev_polozky'][:43]:<45}{(r['mnozstvi'] or 0):>8}"
                f"{(r['celkem_bez_dph'] or 0):>14,.2f}{(r['celkem_s_dph'] or 0):>12,.2f}"
            )

        self.stdout.write("-" * 135)
        self.stdout.write(f"Celkem položek: {len(rows)}")

        if options["csv"]:
            with open(options["csv"], "w", newline="", encoding="utf-8") as f:
                writer = csv_module.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
                writer.writeheader()
                writer.writerows(rows)
            self.stdout.write(self.style.SUCCESS(f"Uloženo do {options['csv']}"))
