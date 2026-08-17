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
        cost = CostEntry.objects.filter(service_item=sp.cost_item, period=period).first()
        if cost is None or cost.amount_units is None:
            radek["stav"] = "bez fakturovaného množství"
            vysledek.append(radek)
            continue

        # POZOR na koeficient: odecet x koeficient = spotreba (Meter.coefficient).
        # Teplo FM se cte v kWh, ale vykazuje v GJ (koef 0,0036) - fakturovanych
        # 6 GJ tedy odpovida odectu 1666,667, ne 6. Bez tohohle prepoctu prikaz
        # pri prvnim ostrem spusteni srazil T_FM_CELKEM z 1666,667 na 6, cimz se
        # spotreba propadla na 0,0216 GJ. Viz 2026-08-16.
        koef = sp.main_meter.coefficient or Decimal("1")
        hodnota = (cost.amount_units / koef).quantize(Decimal("0.001")) if koef != 1 else cost.amount_units
        radek["hodnota"] = hodnota
        radek["fakturovano"] = cost.amount_units
        radek["koeficient"] = koef

        stavajici = MeterReading.objects.filter(meter=sp.main_meter, period=period).first()
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
