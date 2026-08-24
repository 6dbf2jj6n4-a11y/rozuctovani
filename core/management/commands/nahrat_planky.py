"""Nahraje SVG planky (2D pudorysy) ze slozky na disku do Planku arealu.

Planek se vykresluje z `Floorplan.svg_text` (kopie vykresu v databazi), ne
z ulozeneho souboru - viz komentar u modelu. Tenhle prikaz proto plni
`svg_text`; soubor na R2 nechava byt, protoze k vykreslovani neni potreba
a klice k ulozisti nejsou v kazdem prostredi.

Bez --provest jen zkontroluje a vypise, co by se stalo.
"""
import os
import re

from django.core.management.base import BaseCommand, CommandError

from core.floorplan import kody_ploch
from core.models import Floorplan, Site, Unit


class Command(BaseCommand):
    help = "Nahraje SVG plánky ze složky do Plánků daného areálu."

    def add_arguments(self, parser):
        parser.add_argument("--areal", required=True, help="Název areálu, např. DV")
        parser.add_argument("--slozka", required=True, help="Složka s SVG výkresy")
        parser.add_argument(
            "--nazev", default="",
            help="Předpona názvu plánku, např. „Dvořákova“ → „Dvořákova – 1.NP“. "
                 "Bez ní se použije název souboru.",
        )
        parser.add_argument("--provest", action="store_true", help="Opravdu zapsat.")

    def handle(self, *args, **volby):
        try:
            areal = Site.objects.get(name=volby["areal"])
        except Site.DoesNotExist:
            raise CommandError("Areál %r neexistuje. Máme: %s" % (
                volby["areal"], ", ".join(Site.objects.values_list("name", flat=True))))

        slozka = os.path.expanduser(volby["slozka"])
        if not os.path.isdir(slozka):
            raise CommandError("Složka %r neexistuje." % slozka)

        # .pred_orezem/.pred_texty jsou zalohy, _texty.svg je mezivypocet
        soubory = sorted(
            j for j in os.listdir(slozka)
            if j.lower().endswith(".svg") and "_texty" not in j
        )
        if not soubory:
            raise CommandError("Ve složce %r není žádné SVG." % slozka)

        prostory = set(Unit.objects.filter(site=areal).values_list("name", flat=True))
        chyby = 0
        pouzite = set()

        for jmeno in soubory:
            cesta = os.path.join(slozka, jmeno)
            with open(cesta, encoding="utf-8") as f:
                text = f.read()
            try:
                pronajimane, spolecne = kody_ploch(text)
            except Exception as e:
                self.stderr.write("%-16s NELZE PŘEČÍST: %s" % (jmeno, e))
                chyby += 1
                continue

            patro = re.search(r"(\d+)\s*NP", jmeno, re.I)
            nazev = ("%s – %s.NP" % (volby["nazev"], patro.group(1))
                     if volby["nazev"] and patro else os.path.splitext(jmeno)[0])
            poradi = int(patro.group(1)) * 10 if patro else 0

            self.stdout.write("%-16s → „%s“ (pořadí %d, %.1f MB)" % (
                jmeno, nazev, poradi, len(text) / 1e6))
            self.stdout.write("    plochy: %s%s" % (
                ", ".join(pronajimane) or "žádné",
                "   společné: %s" % ", ".join(spolecne) if spolecne else ""))

            nezname = [k for k in pronajimane if k not in prostory]
            if nezname:
                self.stderr.write("    ✗ ve výkresu jsou plochy, které v areálu "
                                  "neexistují: %s" % ", ".join(nezname))
                chyby += 1
            if not pronajimane:
                self.stderr.write("    ✗ výkres nemá vrstvu s plochami "
                                  "(„plochy_rentex“) nebo je prázdná")
                chyby += 1
            pouzite.update(pronajimane)

            if volby["provest"] and not nezname and pronajimane:
                planek, novy = Floorplan.objects.update_or_create(
                    site=areal, name=nazev,
                    defaults={"svg_text": text, "order": poradi, "is_active": True},
                )
                self.stdout.write(self.style.SUCCESS(
                    "    %s" % ("založeno" if novy else "aktualizováno")))

        nepokryte = sorted(prostory - pouzite)
        if nepokryte:
            self.stdout.write("\nProstory bez plochy ve výkresu: %s" % ", ".join(nepokryte))

        if chyby:
            raise CommandError("\nNalezeno %d chyb, nic se nezapisovalo "
                               "(u výkresů s chybou)." % chyby)
        if not volby["provest"]:
            self.stdout.write(self.style.WARNING(
                "\nJen kontrola. Zápis se spustí s --provest."))
