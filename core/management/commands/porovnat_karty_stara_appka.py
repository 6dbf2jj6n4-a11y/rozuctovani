"""Porovna Karty ze stare aplikace (export klicu do xlsx) s nasi DB - plochy,
najem, klice, pausaly. Jen cte, nic nezapisuje. Daniel 2026-09-27/29.

Export ma sloupce: Karta, DatumOd, Kod, TYP_Polozky, PevnaKC, Jednotek,
Plocha, m2, KCzaM, Fakturovat, Trida. Pevne castky jsou ROCNI (PevnaKC/12),
najem = m2 x KCzaM / 12, Fakturovat -1 = ano.

Parovani Karet: podle kodu klienta v nazvu ("Karta GEHER 2026 - 1" ->
klient s kodem GEHER, pripadne kod, ktery takhle zacina; CALAMARI =
pronajimatel arealu) a nase Karta toho klienta platna k datu
max(dnes, DatumOd) - stara aplikace Karty nedeli, my ano.

    python manage.py porovnat_karty_stara_appka --soubor ~/Desktop/klice_NJ.xlsx
"""
import os
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal as D

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import Client, ClientCard, ServicePoolItem, Site

POLOZKY = {
    "ODKL_SNEHU": "odklizení sněhu v zimních obdobích", "ODPADY_SP": "odvoz komunálního odpadu NJ",
    "UKLID_SPOL": "úklidové služby společných prostor NJ", "OSTRAHA": "ostraha areálu NJ",
    "POZ_OCHR": "pult ochrany ALSYKO", "EZS": "pult ochrany ALSYKO",
}
PAUSALY = {"E_PAUSAL": "hlavní odběr elektro NJ", "T_PAUSAL": "hlavní odběr teplo NJ",
           "W_PAUSAL": "hlavní odběr voda NJ", "O_PAUSAL": "paušál ostatní služby NJ"}


def _d(x):
    return D(str(x or 0))


def _kc(x):
    return _d(x).quantize(D("0.01"))


def _f(b):
    return "ano" if b else "NE"


class Command(BaseCommand):
    help = "Porovná Karty ze staré aplikace (xlsx export klíčů) s naší DB."

    def add_arguments(self, parser):
        parser.add_argument("--soubor", default=os.path.expanduser("~/Desktop/klice_NJ.xlsx"))
        parser.add_argument("--areal", default="NJ")

    def handle(self, *args, **o):
        import openpyxl

        site = Site.objects.filter(name=o["areal"]).first()
        if site is None:
            raise CommandError("Areál %s neexistuje." % o["areal"])
        ws = openpyxl.load_workbook(o["soubor"], data_only=True).active
        radky = [r for r in list(ws.iter_rows(values_only=True))[1:] if r and r[0]]
        po_kartach = defaultdict(list)
        for r in radky:
            po_kartach[r[0].strip()].append(r)
        I = {p.name: p for p in ServicePoolItem.objects.filter(site=site)}
        dnes = timezone.localdate()
        sparovane = set()
        celkem = 0

        for nazev in sorted(po_kartach):
            rr = po_kartach[nazev]
            od = rr[0][1].date() if hasattr(rr[0][1], "date") else rr[0][1]
            karta = self._najdi(nazev, od, dnes, site)
            if karta is None:
                self.stdout.write(self.style.WARNING(f"\n=== {nazev} (od {od:%d.%m.%Y}) → u nás NENÍ"))
                celkem += 1
                continue
            sparovane.add(karta.pk)
            rozdily = self._porovnej(rr, karta, I)
            celkem += len(rozdily)
            self.stdout.write(f"\n=== {nazev} (od {od:%d.%m.%Y}) → #{karta.pk} {karta.client.name} "
                              f"{karta.description} [{karta.valid_from} – {karta.valid_to or '…'}]")
            self.stdout.write("   " + ("\n   ".join(rozdily) if rozdily else self.style.SUCCESS("✓ sedí")))

        # nase Karty platne dnes nebo pozdeji, ktere v exportu nejsou
        nase = (ClientCard.objects.filter(card_units__unit__site=site).distinct().select_related("client")
                .exclude(valid_to__lt=dnes).exclude(pk__in=sparovane).order_by("client__name", "valid_from"))
        if nase:
            self.stdout.write(self.style.WARNING("\n=== U nás navíc (platné dnes nebo později, v exportu nejsou):"))
            for k in nase:
                self.stdout.write(f"   #{k.pk} {k.client.name} | {k.description} | {k.valid_from} – {k.valid_to or '…'}"
                                  f"{' | pronajímatel' if k.client_id == site.landlord_id else ''}")
        self.stdout.write(f"\nrozdílů celkem: {celkem}")

    def _najdi(self, nazev, od, dnes, site):
        m = re.match(r"Karta\s+(\S+)\s", nazev)
        kod = m.group(1) if m else ""
        # klient podle nasi Karty se stejnym popisem, pak podle kodu
        stejna = ClientCard.objects.filter(description=nazev).select_related("client").first()
        klient = stejna.client if stejna else Client.objects.filter(code=kod).first()
        if klient is None and kod in ("CALAMARI", "CSE"):
            klient = site.landlord
        if klient is None:
            klient = Client.objects.filter(code__startswith=kod).first()
        if klient is None:
            return None
        k_datu = max(dnes, od)
        karty = [k for k in ClientCard.objects.filter(client=klient, card_units__unit__site=site).distinct()
                 if k.valid_from <= k_datu and (k.valid_to is None or k.valid_to >= k_datu)]
        return sorted(karty, key=lambda k: k.valid_from)[-1] if karty else None

    def _porovnej(self, rr, karta, I):
        out = []
        klice = list(karta.allocation_keys.select_related("service_item", "meter"))
        EL, TE, VO = I.get("hlavní odběr elektro NJ"), I.get("hlavní odběr teplo NJ"), I.get("hlavní odběr voda NJ")

        # plochy a najem
        stare = {}
        for r in rr:
            if r[10] == "NAJEM":
                stare[r[2]] = r
        nase = {cu.unit.name: cu for cu in karta.card_units.select_related("unit")}
        for jmeno in list(stare):
            if jmeno not in nase and jmeno.startswith("A ") and "AB " + jmeno[2:] in nase:
                stare["AB " + jmeno[2:]] = stare.pop(jmeno)
        for u in sorted(set(stare) | set(nase)):
            r, cu = stare.get(u), nase.get(u)
            if cu is None:
                out.append(f"plocha {u}: CHYBÍ u nás (stará {r[7]} m², {_kc(_d(r[7]) * _d(r[8]) / 12)} Kč/měs)")
                continue
            if r is None:
                out.append(f"plocha {u}: jen u nás ({cu.area_m2} m², {cu.monthly_rent} Kč/měs)")
                continue
            if _d(r[7]) != cu.area_m2:
                out.append(f"plocha {u}: výměra stará {r[7]} | naše {cu.area_m2}")
            najem = _kc(_d(r[7]) * _d(r[8]) / 12)
            if abs(najem - (cu.monthly_rent or D(0))) > D("0.5"):
                out.append(f"plocha {u}: nájem stará {najem} Kč/měs | naše {cu.monthly_rent}")

        # elektro po meridlech
        e_stare = {r[2]: r for r in rr if r[10] == "ELEKTRO" and r[3] == "K_CELKU"}
        e_nase = {k.meter.code: k for k in klice if k.meter and EL and k.service_item_id == EL.id}
        for kod in sorted(set(e_stare) | set(e_nase)):
            r, k = e_stare.get(kod), e_nase.get(kod)
            if k is None:
                out.append(f"elektro {kod}: CHYBÍ u nás (stará váha {r[5]}, fakt={_f(r[9])})")
            elif r is None:
                out.append(f"elektro {kod}: jen u nás (váha {k.vaha}, fakt={_f(k.is_billed)})")
            elif _d(r[5]) != (k.vaha or 0) or bool(r[9]) != k.is_billed:
                out.append(f"elektro {kod}: stará {r[5]} fakt={_f(r[9])} | naše {k.vaha} fakt={_f(k.is_billed)}")

        # pausaly a internet
        for kod, nazev in PAUSALY.items():
            r = next((x for x in rr if x[2] == kod), None)
            pol = I.get(nazev)
            ks = [k for k in klice if pol and k.service_item_id == pol.id and k.allocation_type == "fixed_amount"]
            nase_kc = sum((k.value or 0 for k in ks), D(0))
            if r and (not ks or _kc(nase_kc) != _kc(_d(r[4]) / 12) or any(k.is_billed != bool(r[9]) for k in ks)):
                out.append(f"paušál {kod}: stará {_kc(_d(r[4]) / 12)} Kč/měs fakt={_f(r[9])} | naše {_kc(nase_kc) if ks else '–'}")
            elif not r and ks:
                out.append(f"paušál {kod}: jen u nás {_kc(nase_kc)} Kč/měs")
        r = next((x for x in rr if x[2] == "INTERNET" and _d(x[4])), None)
        pol = I.get("připojení k internetu NONSTOP")
        k = next((k for k in klice if pol and k.service_item_id == pol.id), None)
        if r and (k is None or _kc(k.value) != _kc(_d(r[4]) / 12) or k.is_billed != bool(r[9])):
            out.append(f"internet: stará {_kc(_d(r[4]) / 12)} fakt={_f(r[9])} | naše {k and _kc(k.value)} fakt={k and _f(k.is_billed)}")
        elif not r and k:
            out.append(f"internet: jen u nás {_kc(k.value)} fakt={_f(k.is_billed)}")

        # teplo: T_CELKEM = vytapene m2 (T_INDIVIDUALNI), T_SPOLECNA = osoby
        for kod, mer in (("T_CELKEM", "T_INDIVIDUALNI"), ("T_SPOLECNA", "T_SPOLECNA")):
            r = next((x for x in rr if x[2] == kod and _d(x[5])), None)
            k = next((k for k in klice if TE and k.service_item_id == TE.id and k.meter and k.meter.code == mer), None)
            if r and k is None:
                out.append(f"teplo {kod}: stará {r[5]} fakt={_f(r[9])} | u nás klíč {mer} není")
            elif k is not None and r is None:
                out.append(f"teplo {kod}: jen u nás {mer} {k.vaha} fakt={_f(k.is_billed)}")
            elif r and ((k.vaha or 0) != _d(r[5]) or k.is_billed != bool(r[9])):
                out.append(f"teplo {kod}: stará {r[5]} fakt={_f(r[9])} | naše {k.vaha} fakt={_f(k.is_billed)}")

        # voda
        r = next((x for x in rr if x[2] == "W_CELKEM"), None)
        k = next((k for k in klice if VO and k.service_item_id == VO.id and k.allocation_type != "fixed_amount"), None)
        if r and k is None:
            out.append(f"voda: CHYBÍ u nás (stará {r[5]} osob)")
        elif r and ((k.vaha or 0) != _d(r[5]) or k.is_billed != bool(r[9])):
            out.append(f"voda: stará {r[5]} fakt={_f(r[9])} | naše {k.vaha} ({k.weight_source or 'ručně'}) fakt={_f(k.is_billed)}")
        elif k is not None and r is None:
            out.append(f"voda: jen u nás {k.vaha}")

        # srazkove
        r = next((x for x in rr if x[2] == "W_SRAZKOV"), None)
        pol = I.get("srážkové vody NJ")
        k = next((k for k in klice if pol and k.service_item_id == pol.id), None)
        if r and k is None:
            out.append(f"srážkové: CHYBÍ u nás ({r[7]} m²)")
        elif r and ((k.vaha or 0) != _d(r[7]) or k.is_billed != bool(r[9])):
            out.append(f"srážkové: stará {r[7]} m² fakt={_f(r[9])} | naše {k.vaha} fakt={_f(k.is_billed)}")
        elif k is not None and r is None:
            out.append(f"srážkové: jen u nás {k.vaha} m²")

        # ostatni sluzby
        videno = set()
        for kod, nazev in POLOZKY.items():
            r = next((x for x in rr if x[2] == kod), None)
            pol = I.get(nazev)
            k = next((k for k in klice if pol and k.service_item_id == pol.id), None)
            if r is None:
                if k is not None and nazev not in videno and not any(x[2] in (kk for kk, nn in POLOZKY.items() if nn == nazev) for x in rr):
                    out.append(f"{nazev}: jen u nás (váha {k.vaha}, fakt={_f(k.is_billed)})")
                    videno.add(nazev)
                continue
            videno.add(nazev)
            if k is None:
                out.append(f"{kod}: CHYBÍ u nás klíč '{nazev}' (stará váha {r[5]}, fakt={_f(r[9])})")
                continue
            stara = _d(r[5]) if r[3] == "K_CELKU" else _d(r[4]) / 12
            if (k.vaha or 0) != stara or k.is_billed != bool(r[9]):
                out.append(f"{kod}: stará {stara.normalize()} fakt={_f(r[9])} | naše {k.vaha} ({k.weight_source or 'ručně'}) fakt={_f(k.is_billed)}")
        for kod in ("W_VLASTNI", "E_VLASTNI", "UKLID_SLUZ"):
            r = next((x for x in rr if x[2] == kod), None)
            if r:
                out.append(f"{kod}: ve staré ({r[3]}, váha {r[5]}, m² {r[7]}) - u nás bez protějšku")
        return out
