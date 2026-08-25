"""
Prevede SVG, ve kterem jsou plochy pojmenovane primo v `id` tvaru, do
podoby, jakou ceka aplikace: vrstvy `podklad`, `plochy_rentex`
a `Plochy_spolecne` (viz core/floorplan.py).

Kresli se to tak, ze se v Inkscapu klikne na plochu a v Vlastnostech
objektu se ji nastavi ID podle Pronajimaneho prostoru. Tenhle prikaz pak
tvary roztridi do vrstev - rucne by to znamenalo vyrabet vrstvy
a presouvat mezi nimi objekt po objektu.

Tvar se zaradi podle sveho `id`:
  * odpovida Prostoru v arealu   -> vrstva `plochy_rentex`
  * je v seznamu spolecnych      -> vrstva `Plochy_spolecne`
  * cokoliv jineho               -> zustane v podkladu a vypise se

VYCHOZI je jen NAHLED, zapisuje se az s --provest (puvodni soubor se
zalohuje jako .pred_prevodem).

Pouziti:
  python manage.py prevest_planek --soubor plan.svg --areal NJ
  python manage.py prevest_planek --soubor plan.svg --areal NJ --provest
"""
import os
import re
import xml.etree.ElementTree as ET

from django.core.management.base import BaseCommand, CommandError

from core.floorplan import (
    INKSCAPE_NS, SVG_NS, TVARY, VRSTVA_PRONAJIMANE, VRSTVA_SPOLECNE, id_na_nazev,
)
from core.models import Site, Unit

SVG = "{%s}" % SVG_NS
INK = "{%s}" % INKSCAPE_NS

# Co se pozna jako spolecny prostor - jeho `id` nema pro aplikaci vyznam,
# rozhoduje jen vrstva, ve ktere lezi.
SPOLECNE = ("chodba", "schodiste", "kotelna", "rozvodna", "wc", "uklid",
            "denni_mistnost", "kuchynka", "vytah", "spolecne")


class Command(BaseCommand):
    help = "Roztřídí tvary v SVG do vrstev podklad / plochy_rentex / Plochy_spolecne."

    def add_arguments(self, parser):
        parser.add_argument("--soubor", required=True, help="Cesta k SVG")
        parser.add_argument("--areal", required=True, help="Název areálu, např. NJ")
        parser.add_argument("--provest", action="store_true", help="Skutečně zapsat.")

    def handle(self, *args, **volby):
        cesta = os.path.expanduser(volby["soubor"])
        if not os.path.isfile(cesta):
            raise CommandError("Soubor %r neexistuje." % cesta)
        areal = Site.objects.filter(name=volby["areal"]).first()
        if areal is None:
            raise CommandError("Areál %r neexistuje." % volby["areal"])
        prostory = set(Unit.objects.filter(site=areal).values_list("name", flat=True))

        for predpona, adresa in (("svg", SVG_NS), ("inkscape", INKSCAPE_NS),
                                 ("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"),
                                 ("xlink", "http://www.w3.org/1999/xlink")):
            ET.register_namespace(predpona, adresa)
        strom = ET.parse(cesta)
        koren = strom.getroot()
        rodic = {d: r for r in koren.iter() for d in r}

        pronajimane, spolecne, nezname = [], [], []
        for prvek in list(koren.iter()):
            if prvek.tag.split("}")[-1] not in TVARY:
                continue
            sifra = prvek.get("id") or ""
            nazev = id_na_nazev(sifra)
            if nazev in prostory:
                pronajimane.append((prvek, nazev))
            elif re.sub(r"\d+$", "", sifra).lower().rstrip("_") in SPOLECNE:
                spolecne.append((prvek, sifra))
            elif sifra and not re.fullmatch(r"(path|rect|circle|ellipse|polygon|g)\d*", sifra):
                nezname.append((prvek, sifra))

        self.stdout.write(self.style.MIGRATE_HEADING(
            "pronajímané plochy ({}) -> vrstva {}".format(len(pronajimane), VRSTVA_PRONAJIMANE)))
        self.stdout.write("   " + ", ".join(sorted(n for _, n in pronajimane)))
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\nspolečné prostory ({}) -> vrstva {}".format(len(spolecne), VRSTVA_SPOLECNE)))
        self.stdout.write("   " + (", ".join(sorted(s for _, s in spolecne)) or "žádné"))
        if nezname:
            self.stderr.write(self.style.WARNING(
                "\npojmenované tvary, které v areálu {} nemají Prostor ({}) "
                "- zůstanou v podkladu:".format(areal.name, len(nezname))))
            self.stderr.write("   " + ", ".join(sorted(s for _, s in nezname)))

        chybi = sorted(prostory - {n for _, n in pronajimane})
        if chybi:
            self.stdout.write("\nProstory areálu bez plochy ve výkresu ({}): {}".format(
                len(chybi), ", ".join(chybi[:20]) + ("..." if len(chybi) > 20 else "")))

        if not volby["provest"]:
            self.stdout.write(self.style.WARNING("\nJen náhled. Zápis se spustí s --provest."))
            return
        if not pronajimane:
            raise CommandError("\nŽádná plocha se nespárovala, nemá smysl nic zapisovat.")

        # puvodni vrstvy zustavaji jako podklad, jen se prejmenuji
        for g in koren.findall(SVG + "g"):
            if g.get(INK + "groupmode") == "layer" and g.get(INK + "label") not in (
                    VRSTVA_PRONAJIMANE, VRSTVA_SPOLECNE):
                g.set(INK + "label", "podklad")
                g.set("{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}insensitive", "true")

        for nazev_vrstvy, prvky in ((VRSTVA_PRONAJIMANE, pronajimane),
                                    (VRSTVA_SPOLECNE, spolecne)):
            if not prvky:
                continue
            # pri opakovanem spusteni se pouzije uz existujici vrstva,
            # jinak by jich v souboru pribyvalo nekolik stejnojmennych
            vrstva = next(
                (g for g in koren.findall(SVG + "g")
                 if g.get(INK + "label") == nazev_vrstvy), None)
            if vrstva is None:
                vrstva = ET.SubElement(koren, SVG + "g", {
                    "id": "vrstva-" + nazev_vrstvy.lower(),
                    INK + "groupmode": "layer", INK + "label": nazev_vrstvy,
                })
            for prvek, _ in prvky:
                rodic[prvek].remove(prvek)
                vrstva.append(prvek)

        zaloha = cesta + ".pred_prevodem"
        if not os.path.exists(zaloha):
            os.rename(cesta, zaloha)
            self.stdout.write("\nzáloha: {}".format(zaloha))
        strom.write(cesta, encoding="utf-8", xml_declaration=True)
        self.stdout.write(self.style.SUCCESS(
            "\nHotovo - {} pronajímaných a {} společných ploch.".format(
                len(pronajimane), len(spolecne))))
