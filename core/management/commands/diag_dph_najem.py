"""
Diagnostika k DPH u nájmu: porovná, zda je nájem ve Flexi fakturován
s DPH nebo bez, proti našemu příznaku Client.vat_payer.

Slouží jako podklad pro koeficient DPH v sestavě Přehled nájemného
(poměr nájmů bez DPH ku nájmům s DPH) - viz konverzace s Danielem
2026-08-18. Read-only, nic nemění.

Použití:
  python manage.py diag_dph_najem 07/2026
  python manage.py diag_dph_najem 07/2026 --dump-fields
"""
import unicodedata

from django.core.management.base import BaseCommand, CommandError

from core.flexi_client import FlexiAPIError, FlexiClient
from core.models import Client, Period


def _normalize(name):
    """Stejný párovací klíč jako porovnat_najem_flexi._normalize -
    oba systémy píší názvy firem jinak ("s.r.o." vs "s. r. o.")."""
    decomposed = unicodedata.normalize("NFKD", name or "")
    without_diacritics = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in without_diacritics.lower() if c.isalnum())


class Command(BaseCommand):
    help = "Porovná DPH na fakturách nájmu ve Flexi s příznakem Plátce DPH u klienta."

    def add_arguments(self, parser):
        parser.add_argument("period", type=str, help="MM/YYYY, např. 07/2026")
        parser.add_argument(
            "--dump-fields", action="store_true",
            help="Vypíše všechna pole první faktury (kontrola názvů polí ve Flexi).",
        )

    def handle(self, *args, **options):
        try:
            month_str, year_str = options["period"].split("/")
            month, year = int(month_str), int(year_str)
        except ValueError:
            raise CommandError("Období zadej ve formátu MM/YYYY, např. 07/2026")

        if not Period.objects.filter(year=year, month=month).exists():
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
            raise CommandError(f"Chybí env proměnná {e}")
        except FlexiAPIError as e:
            raise CommandError(f"Flexi API chyba {e.status_code}: {e.response_body}")

        if not invoices:
            raise CommandError(f"Ve Flexi nejsou žádné faktury s popisem '{popis}'.")

        if options["dump_fields"]:
            self.stdout.write(f"Pole první faktury ({len(invoices)} faktur celkem):\n")
            for key in sorted(invoices[0]):
                self.stdout.write(f"  {key} = {invoices[0][key]!r}")
            return

        vat_payer_by_key = {
            _normalize(c.name): c.vat_payer for c in Client.objects.all()
        }
        name_by_key = {_normalize(c.name): c.name for c in Client.objects.all()}

        self.stdout.write(
            f"DPH u nájmu za {popis} - Flexi ({len(invoices)} faktur) vs. Client.vat_payer\n"
        )
        self.stdout.write(
            f"{'Klient':<38}{'Základ':>12}{'Celkem':>12}{'DPH':>11}"
            f"{'Fakt. s DPH':>13}{'Plátce u nás':>14}"
        )
        self.stdout.write("-" * 100)

        neshody = []
        souhrn = {"s_dph": 0.0, "bez_dph": 0.0}
        radky = []
        for inv in invoices:
            name = inv.get("nazFirmy") or (inv.get("firma@showAs") or "").split(":", 1)[-1].strip()
            key = _normalize(name)
            zaklad = float(inv.get("sumZkl") or 0)
            celkem = float(inv.get("sumCelkem") or 0)
            dph = celkem - zaklad
            # Rozhoduje skutecne vycislene DPH na fakture, ne sazba u
            # polozky - faktura muze mit sazbu vyplnenou a pritom nulovou
            # zakladnu (osvobozeno), coz je prave ten pripad, ktery nas zajima.
            s_dph = round(dph, 2) > 0
            plátce = vat_payer_by_key.get(key)

            radky.append((name, zaklad, celkem, dph, s_dph, plátce))
            if s_dph:
                souhrn["s_dph"] += zaklad
            else:
                souhrn["bez_dph"] += zaklad

        for name, zaklad, celkem, dph, s_dph, plátce in sorted(radky, key=lambda r: r[0]):
            if plátce is None:
                plátce_txt = "? nenalezen"
                flag = "  <- klient nenalezen v naší DB"
            else:
                plátce_txt = "ANO" if plátce else "NE"
                flag = ""
                if s_dph != bool(plátce):
                    flag = "  <- NESEDÍ"
                    neshody.append((name, s_dph, plátce))

            row = (
                f"{name[:36]:<38}{zaklad:>12,.2f}{celkem:>12,.2f}{dph:>11,.2f}"
                f"{('ANO' if s_dph else 'NE'):>13}{plátce_txt:>14}"
            )
            if flag:
                self.stdout.write(self.style.WARNING(row + flag))
            else:
                self.stdout.write(row)

        celkem_zaklad = souhrn["s_dph"] + souhrn["bez_dph"]
        self.stdout.write("-" * 100)
        self.stdout.write(f"Základ fakturovaný s DPH : {souhrn['s_dph']:>14,.2f} Kč")
        self.stdout.write(f"Základ fakturovaný bez DPH: {souhrn['bez_dph']:>14,.2f} Kč")
        self.stdout.write(f"Základ celkem             : {celkem_zaklad:>14,.2f} Kč")
        if celkem_zaklad:
            podil = souhrn["s_dph"] / celkem_zaklad * 100
            self.stdout.write(f"\nPodíl nájmu s DPH: {podil:.2f} %  (bez DPH: {100 - podil:.2f} %)")

        if neshody:
            self.stdout.write(
                self.style.WARNING(f"\n{len(neshody)} klient(ů) fakturováno jinak, než odpovídá příznaku Plátce DPH:")
            )
            for name, s_dph, plátce in neshody:
                self.stdout.write(
                    f"  {name}: fakturováno {'s' if s_dph else 'bez'} DPH, "
                    f"u nás plátce = {'ANO' if plátce else 'NE'}"
                )
        else:
            self.stdout.write(self.style.SUCCESS("\nDPH na fakturách odpovídá příznaku Plátce DPH u všech klientů."))
