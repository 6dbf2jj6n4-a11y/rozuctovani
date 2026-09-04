"""
Prepise Fakturovane mnozstvi z Nakladu za obdobi do Privodnich meridel
odbernych mist - aby se "dodáno" v reportu Spotřeby měřidel nemuselo
zadavat dvakrat (jednou jako naklad, podruhe jako odecet).

Bere se jen z polozky, kterou ma odberne misto vyslovene nastavenou
(SupplyPoint.cost_item). Hadat ji podle arealu a tridy nejde - teplo NJ
ma dve polozky (pelety a zalozni elektrokotel) a u vody by se pripletly
srazkove vody, ktere v jednotkach nesou m2 plochy, ne m3.
Viz konverzace s Danielem 2026-08-16.

Stejnou funkci vola i akce "Dotáhnout fakturovaná množství do přívodních
měřidel" u Obdobi v adminu.

Pouziti:
  python manage.py dotahnout_fakturovana_mnozstvi --period=07/2026
  python manage.py dotahnout_fakturovana_mnozstvi --period=07/2026 --provest
"""
import calendar
from datetime import date

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from core.models import CostEntry, MeterReading, Period, SupplyPoint


def dotahnout(period, write=False):
    """Vraci seznam radku (dict) s tim, co se (ne)provedlo. Bez `write`
    jen spocita nahled a nic nezapisuje."""
    vysledek = []
    supplies = (
        SupplyPoint.objects
        .exclude(cost_item__isnull=True)
        .exclude(main_meter__isnull=True)
        .select_related("main_meter", "cost_item", "site")
        .order_by("site__name", "meter_type", "name")
    )
    for sp in supplies:
        radek = {"supply": sp, "meter": sp.main_meter, "item": sp.cost_item}
        # Polozka muze mit vic faktur od ruznych dodavatelu - do privodniho
        # meridla patri jejich SOUCET, ale jen kdyz jdou secist (stejna
        # jednotka). Pri ruznych jednotkach (pelety v kg vs elektrokotel
        # v kWh) neni co zapsat.
        # Do meridla, ktere nekdo fyzicky odecita (rezim "stav"), se
        # fakturovane mnozstvi zapsat NESMI - prepsalo by spravcuv odecet
        # a mesicni mnozstvi z faktury navic jako kumulativni stav nedava
        # smysl. Presne to hrozilo u vody NJ, jakmile ji zacal Olda
        # odecitat. Vazba na Naklad u takoveho odberu zustava - slouzi
        # k porovnani "privod vs. faktura" v Prehledu spotreb.
        # Viz Daniel 2026-09-04.
        if sp.main_meter.reading_mode != sp.main_meter.ReadingMode.CONSUMPTION:
            radek["stav"] = "přívod se odečítá ručně (režim „stav“) - nepřepisuji"
            vysledek.append(radek)
            continue

        totals = CostEntry.totals_for(sp.cost_item, period)
        if totals["count"] == 0:
            radek["stav"] = "bez fakturovaného množství"
            vysledek.append(radek)
            continue
        if totals["units"] is None:
            radek["stav"] = (
                f"{totals['count']}× faktura s různými jednotkami - množství nelze sečíst"
                if totals["count"] > 1 else "bez fakturovaného množství"
            )
            vysledek.append(radek)
            continue

        # POZOR na koeficient: odecet x koeficient = spotreba (Meter.coefficient).
        # Teplo FM se cte v kWh, ale vykazuje v GJ (koef 0,0036) - fakturovanych
        # 6 GJ tedy odpovida odectu 1666,667, ne 6. Bez tohohle prepoctu prikaz
        # pri prvnim ostrem spusteni srazil T_FM_CELKEM z 1666,667 na 6, cimz se
        # spotreba propadla na 0,0216 GJ. Viz 2026-08-16.
        koef = sp.main_meter.coefficient or Decimal("1")
        fakturovano = totals["units"]
        hodnota = (fakturovano / koef).quantize(Decimal("0.001")) if koef != 1 else fakturovano
        radek["hodnota"] = hodnota
        radek["fakturovano"] = fakturovano
        radek["koeficient"] = koef

        stavajici = MeterReading.objects.filter(meter=sp.main_meter, period=period).first()
        if stavajici is not None and stavajici.created_by_id is not None:
            # Odecet, ktery nekdo zapsal rucne, se neprepisuje - je to
            # samostatne mereni a v Prehledu spotreb se porovnava proti
            # fakture. Vlastni drivejsi zapisy tohohle prikazu maji
            # "Zadal" prazdne, takze se aktualizovat porad daji.
            # Bez teto pojistky by srpnovy odecet tepla FM (David, 1233)
            # prepsalo fakturovanych 6 GJ. Viz Daniel 2026-09-04.
            radek["hodnota"] = hodnota
            radek["stav"] = "odečet zapsal {} - nepřepisuji (rozdíl vidíš v Přehledu spotřeb)".format(
                stavajici.created_by.get_full_name() or stavajici.created_by.username)
            vysledek.append(radek)
            continue
        if stavajici is not None:
            if stavajici.value == hodnota:
                radek["stav"] = "sedí, beze změny"
            else:
                radek["stav"] = f"přepsat {stavajici.value} → {hodnota}"
                if write:
                    stavajici.value = hodnota
                    try:
                        stavajici.full_clean()
                    except ValidationError as exc:
                        radek["stav"] = "; ".join(exc.messages)
                        vysledek.append(radek)
                        continue
                    stavajici.save()
            vysledek.append(radek)
            continue

        radek["stav"] = f"zapsat {hodnota}"
        if write:
            posledni_den = calendar.monthrange(period.year, period.month)[1]
            novy = MeterReading(
                meter=sp.main_meter, period=period, value=hodnota,
                reading_date=date(period.year, period.month, posledni_den),
                note="fakturováno dodavatelem",
            )
            try:
                novy.full_clean()
            except ValidationError as exc:
                radek["stav"] = "; ".join(exc.messages)
                vysledek.append(radek)
                continue
            novy.save()
        vysledek.append(radek)
    return vysledek


class Command(BaseCommand):
    help = "Přepíše fakturovaná množství z Nákladů do přívodních měřidel odběrných míst."

    def add_arguments(self, parser):
        parser.add_argument("--period", required=True, help="Období MM/RRRR.")
        parser.add_argument("--provest", action="store_true", help="Skutečně zapsat.")

    def handle(self, *args, **options):
        try:
            month, year = options["period"].split("/")
            period = Period.objects.filter(year=int(year), month=int(month)).first()
        except ValueError:
            raise CommandError("Období zadej jako MM/RRRR, např. 07/2026.")
        if period is None:
            raise CommandError(f"Období {options['period']} v databázi není.")

        write = options["provest"]
        if not write:
            self.stdout.write(self.style.WARNING("NÁHLED - nic se nezapisuje (--provest).\n"))

        radky = dotahnout(period, write=write)
        if not radky:
            self.stdout.write(
                "Žádné odběrné místo nemá vyplněný „Náklad, ze kterého brát "
                "fakturované množství“ - doplň ho v Odběrných místech."
            )
            return
        for r in radky:
            self.stdout.write(
                f"  {r['supply'].site.name:3} {r['supply'].name[:18]:18} "
                f"{r['meter'].code:16} ← {r['item'].name[:28]:28} {r['stav']}"
                + (f"  (fakturováno {r['fakturovano']} ÷ koef {r['koeficient']})"
                   if r.get("koeficient") not in (None, 1) else "")
            )
        if not write:
            self.stdout.write(self.style.WARNING("\nNic zapsáno nebylo (--provest)."))
