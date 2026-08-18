"""
Natahne naklady na energie z prijatych faktur v ABRA Flexi a zapise je
jako Naklady za obdobi (CostEntry).

Faktury se poznaji podle popisu ve tvaru "TRIDA MM/RRRR" (napr.
"ELEKTRO 07/2026", "VODA 07/2026", "TEPLO 07/2026") - kvartalni faktury
maji rozsah, napr. "SRAZKY 04-06/2026", a jejich castka se deli rovnym
dilem mezi dotcene mesice.

Na kterou polozku zasobniku naklad patri urcuje kombinace TRIDA +
STREDISKO + DODAVATEL - podle popisu samotneho to nejde, protoze:
  - elektrina FM prichazi od TRI dodavatelu (ALTIN = odber EAN 668,
    TEDOME a SZYPKAR = hlavni odber),
  - faktura SMVAK pro NJ obsahuje VODU I SRAZKOVE dohromady, takze se
    musi rozdelit podle POLOZEK faktury (nazev VODA / SRAZKY).
Viz konverzace s Danielem 2026-08-17.

Castky se berou BEZ DPH (hlavicka sumZklCelkem, u polozek sumZkl).
Existujici naklady se NEPREPISUJI - jen se nahlasi, ze uz tam jsou
(drobne halerove rozdily proti Flexi jsou v poradku).

VYCHOZI je jen NAHLED, zapisuje se az s --provest.

Pouziti:
  python manage.py import_naklady_flexi --od=01/2026
  python manage.py import_naklady_flexi --od=01/2026 --provest
"""
import re
from decimal import Decimal

import requests
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from core.flexi_client import FlexiClient
from core.models import CostEntry, Period, ServicePoolItem

POPIS = re.compile(
    r"^\s*(ELEKTRO|VODA|TEPLO|SRAZKY|SRÁŽKOVÉ?)\s+(\d{1,2})(?:\s*-\s*(\d{1,2}))?/(\d{4})",
    re.IGNORECASE,
)

# (trida z popisu, stredisko, kod dodavatele) -> (nazev polozky, nazev dodavatele
# do CostEntry.supplier). Dodavatel None = na polozce je jen jedna faktura,
# supplier se nevyplnuje.
MAPOVANI = {
    ("ELEKTRO", "FM", "ALTIN"): ("odběr EAN 668 FM", None),
    ("ELEKTRO", "FM", "TEDOME"): ("hlavní odběr elektro FM", "TEDOM EAN 240"),
    ("ELEKTRO", "FM", "SZYPKAR"): ("hlavní odběr elektro FM", "SZYPKA EAN"),
    ("ELEKTRO", "NJ", "TEDOME"): ("hlavní odběr elektro NJ", None),
    ("TEPLO", "FM", "VEOLIA"): ("hlavní odběr teplo FM", None),
    # TEPLO NJ (pelety) se zamerne NEMAPUJE - Daniel je zadava sam vcetne
    # mnozstvi v kg. Viz konverzace 2026-08-17.
    ("VODA", "FM", "SMVAK"): ("hlavní odběr voda FM", None),
    ("VODA", "NJ", "SMVAK"): ("hlavní odběr voda NJ", None),
    ("SRAZKY", "FM", "SMVAK"): ("srážkové vody FM", None),
    ("SRAZKY", "NJ", "SMVAK"): ("srážkové vody NJ", None),
}

# Nazvy polozek na fakture, ktere znamenaji srazkove vody (faktura SMVAK
# pro NJ nese vodu i srazky dohromady).
SRAZKY_NAZVY = ("SRAZK", "SRÁŽK")


class Command(BaseCommand):
    help = "Natáhne náklady na energie z přijatých faktur v ABRA Flexi."

    def add_arguments(self, parser):
        parser.add_argument("--od", default="01/2026", help="Od období MM/RRRR (výchozí 01/2026).")
        parser.add_argument("--provest", action="store_true", help="Skutečně zapsat.")

    def handle(self, *args, **options):
        try:
            m, y = options["od"].split("/")
            od = (int(y), int(m))
        except ValueError:
            raise CommandError("--od zadej jako MM/RRRR, např. 01/2026.")

        write = options["provest"]
        if not write:
            self.stdout.write(self.style.WARNING("NÁHLED - nic se nezapisuje (--provest).\n"))

        client = FlexiClient()
        faktury = client.list_records(
            "faktura-prijata", "datVyst>='{}-01-01'".format(od[0]),
            extra_params={"limit": "0", "detail": "full"},
        )

        radky = []          # (rok, mesic, klic_mapovani, castka, kod_faktury)
        nerozpoznane = []
        for f in faktury:
            popis = (f.get("popis") or "").strip()
            m = POPIS.match(popis)
            if not m:
                continue
            trida = m.group(1).upper()
            if trida.startswith("SRÁŽ"):
                trida = "SRAZKY"
            rok = int(m.group(4))
            od_m, do_m = int(m.group(2)), int(m.group(3) or m.group(2))
            if (rok, od_m) < od:
                continue
            stred = (f.get("stredisko") or "").replace("code:", "").strip() or "—"
            firma = (f.get("firma") or "").replace("code:", "").strip()
            mesicu = do_m - od_m + 1

            # Faktura muze nest vic druhu plneni (SMVAK NJ = voda + srazky),
            # proto se rozpad bere z POLOZEK, kdyz tam nejaka srazkova je.
            casti = self._rozpad_faktury(client, f, trida)
            for cast_trida, castka in casti:
                klic = (cast_trida, stred, firma)
                if klic not in MAPOVANI:
                    nerozpoznane.append((f.get("kod"), popis, cast_trida, stred, firma, castka))
                    continue
                dil = (castka / mesicu).quantize(Decimal("0.01"))
                for i in range(mesicu):
                    radky.append((rok, od_m + i, klic, dil, f.get("kod"), mesicu > 1))

        if not radky and not nerozpoznane:
            self.stdout.write("Žádné faktury k importu.")
            return

        zapsano = preskoceno = 0
        self.stdout.write("{:8} {:34} {:14} {:>12}  {}".format(
            "období", "položka", "dodavatel", "Kč bez DPH", "faktura"))
        for rok, mesic, klic, castka, kod, deleno in sorted(radky):
            nazev, dodavatel = MAPOVANI[klic]
            period = Period.objects.filter(year=rok, month=mesic).first()
            # Jen id - nacitat cely ServicePoolItem znamena SELECT vsech
            # sloupcu, coz spadne, kdyz je v modelu pole, jehoz migrace
            # jeste neprobehla (soubezna session).
            item_id = (
                ServicePoolItem.objects.filter(name=nazev)
                .values_list("id", flat=True).first()
            )
            if period is None or item_id is None:
                self.stdout.write(self.style.WARNING(
                    "  {:02d}/{} {:34} chybí {}".format(
                        mesic, rok, nazev[:34], "období" if period is None else "položka")))
                continue

            uz = CostEntry.objects.filter(service_item_id=item_id, period=period)
            if dodavatel:
                uz = uz.filter(supplier=dodavatel)
            if uz.exists():
                preskoceno += 1
                self.stdout.write("  {:02d}/{} {:34} {:14} {:>12,.2f}  {} – už zadáno".format(
                    mesic, rok, nazev[:34], dodavatel or "—", castka, kod))
                continue

            znacka = " (1/{} kvartálu)".format(3) if deleno else ""
            self.stdout.write(self.style.SUCCESS(
                "  {:02d}/{} {:34} {:14} {:>12,.2f}  {}{}".format(
                    mesic, rok, nazev[:34], dodavatel or "—", castka, kod, znacka)))
            if write:
                byl_zavreny = period.status == Period.Status.CLOSED
                if byl_zavreny:
                    Period.objects.filter(pk=period.pk).update(status=Period.Status.OPEN)
                    period.refresh_from_db()
                ce = CostEntry(
                    service_item_id=item_id, period=period, amount_czk=castka,
                    supplier=dodavatel or "", note="ABRA {}".format(kod),
                )
                try:
                    # exclude: validace by si tahala cely ServicePoolItem
                    # (viz poznamka u nacteni item_id vyse)
                    ce.full_clean(exclude=["service_item"])
                    ce.save()
                    zapsano += 1
                except ValidationError as exc:
                    self.stdout.write(self.style.ERROR(
                        "      nezapsáno: {}".format("; ".join(exc.messages))))
                finally:
                    if byl_zavreny:
                        Period.objects.filter(pk=period.pk).update(status=Period.Status.CLOSED)

        if nerozpoznane:
            self.stdout.write(self.style.WARNING("\nBEZ MAPOVÁNÍ (přeskočeno):"))
            for kod, popis, trida, stred, firma, castka in nerozpoznane:
                self.stdout.write("  {} | {} | {} / {} / {} | {:,.2f}".format(
                    kod, popis[:26], trida, stred, firma, castka))

        self.stdout.write("\nzapsáno {}, přeskočeno (už zadáno) {}".format(zapsano, preskoceno))
        if not write:
            self.stdout.write(self.style.WARNING("Nic zapsáno nebylo (--provest)."))

    def _rozpad_faktury(self, client, faktura, trida):
        """[(trida, castka_bez_dph)] - obvykle jedna polozka za celou fakturu,
        ale faktura SMVAK pro NJ nese VODU i SRAZKY dohromady, takze se
        rozdeli podle polozek faktury."""
        celkem = Decimal(str(faktura.get("sumZklCelkem") or 0))
        if trida != "VODA":
            return [(trida, celkem)]

        url = "{}/c/{}/faktura-prijata/{}.json?relations=polozkyFaktury&detail=full".format(
            client.url, client.company, faktura.get("id"))
        resp = requests.get(url, auth=(client.user, client.password),
                            headers={"Accept": "application/json"}, timeout=60)
        if resp.status_code != 200:
            return [(trida, celkem)]
        data = (resp.json().get("winstrom", {}).get("faktura-prijata") or [{}])[0]
        polozky = data.get("polozkyFaktury") or []
        voda = srazky = Decimal("0")
        for p in polozky:
            nazev = (p.get("nazev") or "").upper()
            castka = Decimal(str(p.get("sumZkl") or 0))
            if any(s in nazev for s in SRAZKY_NAZVY):
                srazky += castka
            else:
                voda += castka  # vc. radku "zaokrouhlení"
        if srazky:
            return [("VODA", voda), ("SRAZKY", srazky)]
        return [(trida, celkem)]
