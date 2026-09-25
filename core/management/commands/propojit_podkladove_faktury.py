"""
Propoji prijate faktury dodavatelu v ABRA Flexi s polozkami a obdobimi
a PDF zkopiruje na R2, aby je klientsky portal nabidl ke stazeni jako
podkladove faktury. Kopirovani na R2 potrebuje promenne R2_* - lokalne
nejsou, proto se v provozu spousti akci u Obdobi.
Viz core/podkladove_faktury.py a core.models.PodkladovaFaktura.

Naklady se tim nemeni - jde jen o odkaz na doklad. Opakovatelne: uz
propojene faktury se jen aktualizuji (napr. vymenena priloha v ABRA).

VYCHOZI je jen NAHLED, zapisuje se az s --provest.

Pouziti:
  python manage.py propojit_podkladove_faktury --od=08/2026
  python manage.py propojit_podkladove_faktury --od=01/2026 --provest
"""
from django.core.management.base import BaseCommand, CommandError

from core.podkladove_faktury import propojit


class Command(BaseCommand):
    help = "Propojí přijaté faktury v ABRA s položkami a obdobími (podkladové faktury pro portál)."

    def add_arguments(self, parser):
        parser.add_argument("--od", default="01/2026", help="Od období MM/RRRR (výchozí 01/2026).")
        parser.add_argument("--provest", action="store_true", help="Skutečně zapsat.")

    def handle(self, *args, **options):
        try:
            m, y = options["od"].split("/")
            od = (int(y), int(m))
        except ValueError:
            raise CommandError("--od zadej jako MM/RRRR, např. 01/2026.")

        zapsat = options["provest"]
        if not zapsat:
            self.stdout.write(self.style.WARNING("NÁHLED - nic se nezapisuje (--provest).\n"))

        radky, nerozpoznane = propojit(od=od, zapsat=zapsat)
        for obdobi, polozka, kod, dodavatel, soubor, stav in sorted(radky):
            styl = self.style.SUCCESS if stav in ("nová", "změna", "chybí PDF") else (lambda x: x)
            self.stdout.write(styl("  {:8} {:30} {:11} {:28} {:38} {}".format(
                obdobi, polozka[:30], kod, dodavatel[:28], soubor[:38] or "(bez přílohy)", stav)))
        if nerozpoznane:
            self.stdout.write(self.style.WARNING("\nBEZ MAPOVÁNÍ (přeskočeno):"))
            for kod, popis, trida, stred, firma in nerozpoznane:
                self.stdout.write(f"  {kod} | {popis[:26]} | {trida} / {stred} / {firma}")
        nove = sum(1 for r in radky if r[5] in ("nová", "změna", "chybí PDF"))
        self.stdout.write(f"\nnových, změněných nebo bez PDF: {nove}, celkem nalezeno: {len(radky)}")
