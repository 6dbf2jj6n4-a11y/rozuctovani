"""Porovna Karty ze stare aplikace (export klicu do xlsx) s nasi DB - plochy,
najem, klice, pausaly. Jen cte, nic nezapisuje. Daniel 2026-09-27/29.

Export ma sloupce: Karta, DatumOd, Kod, TYP_Polozky, PevnaKC, Jednotek,
Plocha, m2, KCzaM, Fakturovat, Trida (a volitelne IDFIRMA = kod klienta). Pevne castky jsou ROCNI (PevnaKC/12),
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
        parser.add_argument("--k-datu", help="Den, ke kteremu se Karty paruji (RRRR-MM-DD), napr. stred "
                                             "pocitaneho obdobi; vychozi dnes.")

    def handle(self, *args, **o):
        import openpyxl

        site = Site.objects.filter(name=o["areal"]).first()
        if site is None:
            raise CommandError("Areál %s neexistuje." % o["areal"])
        ws = openpyxl.load_workbook(o["soubor"], data_only=True).active
        radky = [r for r in list(ws.iter_rows(values_only=True))[1:] if r and r[0]]
        # radky bez penez se neporovnavaji (pevna castka 0 Kc, plocha x 0 Kc/m2)
        radky = [r for r in radky if not (
            (r[3] == "PEVNA_KC" and not _d(r[4])) or (r[3] == "K_PLOSE" and r[2] != "W_SRAZKOV" and not _d(r[8]))
        )]
        po_kartach = defaultdict(list)
        for r in radky:
            po_kartach[r[0].strip()].append(r)
        I = {p.name: p for p in ServicePoolItem.objects.filter(site=site)}
        dnes = date.fromisoformat(o["k_datu"]) if o.get("k_datu") else timezone.localdate()
        self._k_datu = dnes
        self.stdout.write(f"Karty platné k {dnes:%d. %m. %Y}")
        sparovane = set()
        celkem = 0

        for nazev in sorted(po_kartach):
            rr = po_kartach[nazev]
            od = rr[0][1].date() if hasattr(rr[0][1], "date") else rr[0][1]
            idfirma = (rr[0][11] or "").strip() if len(rr[0]) > 11 else ""
            karta = self._najdi(nazev, od, dnes, site, idfirma)
            if karta is None:
                self.stdout.write(self.style.WARNING(f"\n=== {nazev} (od {od:%d.%m.%Y}) → u nás NENÍ"))
                celkem += 1
                continue
            sparovane.add(karta.pk)
            rozdily = self._porovnej(rr, karta, I)
            if idfirma and idfirma != karta.client.code:
                rozdily.insert(0, f"IDFIRMA stará {idfirma} | kód klienta u nás {karta.client.code}")
            celkem += len(rozdily)
            self.stdout.write(f"\n=== {nazev} (od {od:%d.%m.%Y}) → #{karta.pk} {karta.client.name} "
                              f"{karta.description} [{karta.valid_from} – {karta.valid_to or '…'}]")
            self.stdout.write("   " + ("\n   ".join(rozdily) if rozdily else self.style.SUCCESS("✓ sedí")))

        # nase Karty platne k datu, ktere v exportu nejsou
        nase = (ClientCard.objects.filter(card_units__unit__site=site, valid_from__lte=dnes).distinct()
                .select_related("client").exclude(valid_to__lt=dnes).exclude(pk__in=sparovane)
                .order_by("client__name", "valid_from"))
        if nase:
            self.stdout.write(self.style.WARNING(f"\n=== U nás navíc (platné k {dnes:%d. %m. %Y}, v exportu nejsou):"))
            for k in nase:
                self.stdout.write(f"   #{k.pk} {k.client.name} | {k.description} | {k.valid_from} – {k.valid_to or '…'}"
                                  f"{' | pronajímatel' if k.client_id == site.landlord_id else ''}")
        self.stdout.write(f"\nrozdílů celkem: {celkem}")

    def _najdi(self, nazev, od, dnes, site, idfirma=""):
        m = re.match(r"Karta\s+(\S+)\s", nazev)
        kod = m.group(1) if m else ""
        # klient podle IDFIRMA (= kod klienta = kod v ABRA), pak podle nasi
        # Karty se stejnym popisem, pak podle kodu v nazvu Karty
        klient = Client.objects.filter(code=idfirma).first() if idfirma else None
        if klient is None:
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

    def _polozka(self, I, *zacatky):
        for z in zacatky:
            for nazev, pol in I.items():
                if nazev.startswith(z):
                    return pol
        return None

    def _porovnej(self, rr, karta, I):
        """Obecne pro NJ i FM: klice na meridlech podle kodu meridla, sluzby
        podle nazvu polozky, pausaly a internet po Kc za mesic."""
        from billing.engine import ABSOLUTE_AMOUNT_TYPES, _fixed_amount_for
        from core.models import Period

        out = []
        klice = list(karta.allocation_keys.select_related("service_item", "meter"))
        trida = {
            "ELEKTRO": self._polozka(I, "hlavní odběr elektro"),
            "TEPLO": self._polozka(I, "hlavní odběr teplo"),
            "VODA": self._polozka(I, "hlavní odběr voda"),
        }
        SRAZ = self._polozka(I, "srážkové")
        INTERNET = self._polozka(I, "připojení k internetu")
        EAN668 = self._polozka(I, "odběr EAN 668")
        O_PAUSAL = next((p for p in I.values() if p.pausal_tridy), None)
        SLUZBY = {
            "ODKL_SNEHU": "odklizení sněhu", "ODPADY_SP": "odvoz komunál", "OSTRAHA": "ostraha areálu",
            "UKLID_SPOL": "úklidové služby společných", "UKLID_A": "úklidové služby budova A",
            "UKLID_B": "úklidové služby budova B", "UKLID_D": "úklidové služby budova D",
            "UKLID_N": "úklidové služby budova N", "SERVIS_VYT": "servis výtahů",
            "POZ_OCHR": "revize hasících", "EZS": "pult ochrany",
        }
        PAUSAL_TRIDA = {"E_PAUSAL": "ELEKTRO", "E_PAUS": "ELEKTRO", "T_PAUSAL": "TEPLO",
                        "W_PAUSAL": "VODA", "O_PAUSAL": None}
        obdobi = Period.objects.filter(year=self._k_datu.year, month=self._k_datu.month).first()

        # --- plochy a najem
        stare = {r[2]: r for r in rr if r[10] == "NAJEM"}
        nase = {cu.unit.name: cu for cu in karta.card_units.select_related("unit")}
        for jmeno in list(stare):
            if jmeno in nase:
                continue
            if jmeno.startswith("A ") and "AB " + jmeno[2:] in nase:
                stare["AB " + jmeno[2:]] = stare.pop(jmeno)
                continue
            # stara aplikace nazev plochy orezava na 10 znaku ("F 2.01 SKL")
            kandidati = [n for n in nase if n not in stare and n.startswith(jmeno.rstrip())]
            if not kandidati:
                kandidati = [n for n in nase if n not in stare and jmeno.startswith(n + " ")]
            if len(kandidati) == 1:
                stare[kandidati[0]] = stare.pop(jmeno)
        for u in sorted(set(stare) | set(nase)):
            r, cu = stare.get(u), nase.get(u)
            if r is not None and cu is not None and u.startswith("VÝTAH"):
                # vytah ma ve stare aplikaci "1 m2" jako pocet, u nas 0 m2 - porovna se jen najem
                najem = _kc(_d(r[7]) * _d(r[8]) / 12)
                if abs(najem - (cu.monthly_rent or D(0))) > D("0.5"):
                    out.append(f"plocha {u}: nájem stará {najem} Kč/měs | naše {cu.monthly_rent}")
                continue
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

        # --- ocekavane vahy z exportu: (polozka, meridlo) -> (vaha, fakt, kod)
        cekam, pausaly_stare, bez = {}, defaultdict(lambda: D(0)), []
        pausal_fakt = {}
        for r in rr:
            kod, typ, trida_r = r[2], r[3], r[10]
            if trida_r == "NAJEM":
                continue
            if kod in PAUSAL_TRIDA or kod == "INTERNET":
                pol = INTERNET if kod == "INTERNET" else (O_PAUSAL if PAUSAL_TRIDA[kod] is None else trida[PAUSAL_TRIDA[kod]])
                castka = _d(r[4]) / 12 if typ == "PEVNA_KC" else _d(r[7]) * _d(r[8]) / 12
                if pol is not None:
                    pausaly_stare[pol.id] += castka
                    pausal_fakt[pol.id] = bool(r[9])
                continue
            if kod.startswith("W_SRAZ"):
                cekam[(SRAZ and SRAZ.id, None)] = (_d(r[7]), bool(r[9]), kod)
                continue
            if typ == "PEVNA_KC" and kod in SLUZBY:
                pol = self._polozka(I, SLUZBY[kod])
                if pol is not None:
                    pausaly_stare[pol.id] += _d(r[4]) / 12
                    pausal_fakt[pol.id] = bool(r[9])
                continue
            if kod in SLUZBY:
                pol = self._polozka(I, SLUZBY[kod])
                vaha = _d(r[5]) if typ == "K_CELKU" else (_d(r[7]) if typ == "K_PLOSE" else _d(r[4]) / 12)
                cekam[(pol and pol.id, None)] = (vaha, bool(r[9]), kod)
                continue
            if kod.startswith("668"):
                cekam[(EAN668 and EAN668.id, "668")] = (_d(r[5]), bool(r[9]), kod)
                continue
            if kod.endswith("_VLASTNI") or kod == "UKLID_SLUZ":
                bez.append(f"{kod}: ve staré ({typ}, váha {r[5]}, m² {r[7]}) - u nás bez protějšku")
                continue
            pol = trida.get(trida_r)
            meridlo = {"T_CELKEM": "T_INDIVIDUALNI"}.get(kod, kod)
            if kod == "W_CELKEM":
                meridlo = None
            cekam[(pol and pol.id, meridlo)] = (_d(r[5]), bool(r[9]), kod)

        # --- nase vahy
        mame = {}
        for k in klice:
            if k.allocation_type in ABSOLUTE_AMOUNT_TYPES and k.service_item_id != (SRAZ and SRAZ.id):
                continue
            if not (k.vaha or 0):
                continue  # nulova vaha (revize bez poctu) nic neovlivni
            mer = k.meter.code if k.meter else None
            if EAN668 and k.service_item_id == EAN668.id:
                mer = "668"
            mame[(k.service_item_id, mer)] = (k.vaha, k.is_billed, k)

        jmena = {p.id: p.name for p in I.values()}
        for klic in sorted(set(cekam) | set(mame), key=lambda x: (jmena.get(x[0], ""), x[1] or "")):
            c, m = cekam.get(klic), mame.get(klic)
            popis = f"{jmena.get(klic[0], '?')}{' ' + klic[1] if klic[1] else ''}"
            if m is None:
                out.append(f"{popis}: CHYBÍ u nás (stará {c[2]} váha {c[0].normalize()}, fakt={_f(c[1])})")
            elif c is None:
                out.append(f"{popis}: jen u nás (váha {m[0]}, fakt={_f(m[1])})")
            elif _d(m[0]) != c[0] or m[1] != c[1]:
                out.append(f"{popis}: stará {c[0].normalize()} fakt={_f(c[1])} | naše {m[0]} "
                           f"({m[2].weight_source or 'ručně'}) fakt={_f(m[1])}")

        # --- pausaly a internet po Kc za mesic
        nase_pausaly, nase_fakt = defaultdict(lambda: D(0)), {}
        for k in klice:
            if k.allocation_type not in ABSOLUTE_AMOUNT_TYPES or (SRAZ and k.service_item_id == SRAZ.id):
                continue
            castka = _fixed_amount_for(k, k.service_item, obdobi, []) if obdobi else k.value
            nase_pausaly[k.service_item_id] += castka or D(0)
            nase_fakt[k.service_item_id] = k.is_billed
        for pid in sorted(set(pausaly_stare) | set(nase_pausaly), key=lambda x: jmena.get(x, "")):
            s, n = _kc(pausaly_stare.get(pid, 0)), _kc(nase_pausaly.get(pid, 0))
            if s == 0 and n == 0:
                continue
            if abs(s - n) > D("0.5") or (pid in pausal_fakt and pid in nase_fakt and pausal_fakt[pid] != nase_fakt[pid]):
                out.append(f"pevná částka {jmena.get(pid, '?')}: stará {s} Kč/měs fakt={_f(pausal_fakt.get(pid))} "
                           f"| naše {n} fakt={_f(nase_fakt.get(pid))}")
        return out + bez
