"""
Vychozi stavy meridel arealu DV k 1. 1. 2026 (Danieluv rozpis
stavy_01012026.xlsx).

Zapisuji se do obdobi 12/2025, protoze stav k 1. lednu je stav ke KONCI
prosince - spotreba za 01/2026 pak vyjde jako rozdil proti nemu. Obdobi je
uzavrene, takze se na dobu zapisu docasne otevre a hned zase zavre.

Zaroven zaklada meridla, ktera v DV chybela: elektromery nebytovych
prostor (D1, E1, H2), spolecne spotreby a vytahu, a hlavni vodomer.
Hlavni vodomer se nastavi jako nadrazeny bytovym vodomerum - stejne jako
na FM, aby system sam dopocital ztratu a nezmerenou spotrebu.

VYCHOZI je jen NAHLED, zapisuje se az s --provest. Opakovane spusteni uz
nic nemeni (co existuje, se preskoci).

Pouziti:
  python manage.py import_stavy_dv
  python manage.py import_stavy_dv --provest
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from core.models import Meter, MeterReading, Period, Site

# prostor -> (voda m3, teplo GJ, elektro kWh nebo None)
STAVY = [
    ("D1", 247, 350, 13585),
    ("E1", 97, 254, 11122),
    ("F1", 891, 265, None),
    ("F2", 685, 181, None),
    ("F3", 636, 125, None),
    ("F4", 785, 282, None),
    ("G1", 516, 191, None),
    ("G2", 645, 210, None),
    ("G3", 585, 184, None),
    ("H1", 217, 91, None),
    ("H2", 747, 177, 16518),
]

# meridla, ktera nepatri ke konkretnimu prostoru
SPOLECNA = [
    ("W_DV_CELKEM", "voda", "m³", "hlavní přívod vody", 363),
    ("E_SPOL", "elektro", "kWh", "společná spotřeba", 87500),
    ("E_VYTAH", "elektro", "kWh", "výtah", 7797),
]

OBDOBI = (2025, 12)
DATUM = date(2025, 12, 31)  # konec obdobi; Danieluv rozpis je "stav k 1. 1. 2026"
POZNAMKA = "Výchozí stav k 1. 1. 2026"


class Command(BaseCommand):
    help = "Zapíše výchozí stavy měřidel areálu DV k 1. 1. 2026 do období 12/2025."

    def add_arguments(self, parser):
        parser.add_argument("--provest", action="store_true", help="Skutečně zapsat.")

    def handle(self, *args, **volby):
        site = Site.objects.filter(name="DV").first()
        if site is None:
            raise CommandError("Areál DV nenalezen.")
        period = Period.objects.filter(year=OBDOBI[0], month=OBDOBI[1]).first()
        if period is None:
            raise CommandError("Období %d/%d neexistuje." % (OBDOBI[1], OBDOBI[0]))

        zapisovat = volby["provest"]
        if not zapisovat:
            self.stdout.write(self.style.WARNING("NÁHLED - nic se nezapisuje (--provest).\n"))

        meridla = {m.code: m for m in Meter.objects.filter(site=site)}

        # ---------------------------------------------------------- měřidla
        self.stdout.write(self.style.MIGRATE_HEADING("1) CHYBĚJÍCÍ MĚŘIDLA"))
        chybejici = []
        for prostor, _voda, _teplo, elektro in STAVY:
            if elektro is not None:
                chybejici.append(
                    ("E_%s" % prostor, "elektro", "kWh", "elektroměr %s" % prostor)
                )
        for kod, trida, jednotka, popis, _stav in SPOLECNA:
            chybejici.append((kod, trida, jednotka, popis))

        for kod, trida, jednotka, popis in chybejici:
            if kod in meridla:
                self.stdout.write("   %-14s už existuje" % kod)
                continue
            self.stdout.write(self.style.SUCCESS(
                "   %-14s %s (%s)" % (kod, popis, jednotka)))
            if zapisovat:
                meridla[kod] = Meter.objects.create(
                    site=site, code=kod, name=popis,
                    meter_type=trida, unit_of_measure=jednotka,
                )

        # ------------------------------------------------------- hierarchie
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n2) HLAVNÍ VODOMĚR JAKO NADŘAZENÝ"))
        hlavni = meridla.get("W_DV_CELKEM")
        podruzne = ["W_%s" % p for p, *_ in STAVY]
        if hlavni is None:
            self.stdout.write("   (W_DV_CELKEM zatím neexistuje - napřed --provest)")
        else:
            for kod in podruzne:
                m = meridla.get(kod)
                if m is None:
                    self.stdout.write(self.style.WARNING("   %-8s neexistuje" % kod))
                elif m.parent_meter_id == hlavni.pk:
                    self.stdout.write("   %-8s už je napojený" % kod)
                else:
                    self.stdout.write(self.style.SUCCESS(
                        "   %-8s -> W_DV_CELKEM" % kod))
                    if zapisovat:
                        m.parent_meter = hlavni
                        m.save(update_fields=["parent_meter"])

        # --------------------------------------------------------- odečty
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n3) ODEČTY do %d/%d (%s)" % (OBDOBI[1], OBDOBI[0], DATUM)))
        k_zapisu = []
        for prostor, voda, teplo, elektro in STAVY:
            for predpona, hodnota in (("W", voda), ("T", teplo), ("E", elektro)):
                if hodnota is not None:
                    k_zapisu.append(("%s_%s" % (predpona, prostor), hodnota))
        for kod, _t, _j, _p, stav in SPOLECNA:
            k_zapisu.append((kod, stav))

        odecteno = 0
        # Obdobi je uzavrene a MeterReading.clean() do nej odecet nepusti.
        # create() by validaci obesel, ale ta ochrana ma svuj duvod - misto
        # obchvatu se obdobi na dobu zapisu otevre a hned zase zavre.
        with self._s_otevrenym_obdobim(period, zapisovat):
            for kod, hodnota in k_zapisu:
                m = meridla.get(kod)
                if m is None:
                    self.stdout.write(self.style.WARNING(
                        "   %-14s měřidlo neexistuje - přeskočeno" % kod))
                    continue
                if MeterReading.objects.filter(meter=m, period=period).exists():
                    self.stdout.write("   %-14s odečet už existuje" % kod)
                    continue
                self.stdout.write(self.style.SUCCESS(
                    "   %-14s %10s %s" % (kod, hodnota, m.unit_of_measure)))
                if zapisovat:
                    odecet = MeterReading(
                        meter=m, period=period, reading_date=DATUM,
                        value=Decimal(str(hodnota)), note=POZNAMKA,
                    )
                    odecet.full_clean()
                    odecet.save()
                    odecteno += 1

        if not zapisovat:
            self.stdout.write(self.style.WARNING("\nNic zapsáno nebylo (--provest)."))
            return

        self.stdout.write(self.style.SUCCESS(
            "\nzapsáno %d odečtů do %d/%d" % (odecteno, OBDOBI[1], OBDOBI[0])))

    def _s_otevrenym_obdobim(self, period, zapisovat):
        """Otevre uzavrene obdobi jen na dobu zapisu a zase ho zavre.

        Vraci se puvodni status i kdyz zapis spadne - jinak by uzavrene
        obdobi zustalo otevrene a nikdo by o tom nevedel."""
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            puvodni = period.status
            zavrene = zapisovat and puvodni == Period.Status.CLOSED
            if zavrene:
                self.stdout.write("   (období %d/%d se na dobu zápisu otevře)"
                                  % (period.month, period.year))
                period.status = Period.Status.OPEN
                period.save(update_fields=["status"])
            try:
                yield
            finally:
                if zavrene:
                    period.status = puvodni
                    period.save(update_fields=["status"])
                    self.stdout.write("   (období %d/%d zase uzavřeno)"
                                      % (period.month, period.year))

        return _ctx()
