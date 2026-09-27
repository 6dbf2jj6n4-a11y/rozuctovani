"""Report Naklady pronajimatele - kolik za obdobi nese pronajimatel areálu
a jak si stoji pausaly proti skutecnym podilum (Daniel 2026-09-27).

Ctyri bloky, vsechno ze spocitanych radku vyuctovani (BillingLine):

1. Pausalni klienti - karty s fakturovanou pevnou castkou, ktera se
   NEodecetla z nakladu (jde navrch = vynos pronajimatele), nebo s radkem
   polozky "Pausal za celou Tridu". Podil = jejich nefakturovane podily
   (kolik by platili podle skutecne spotreby, nese pronajimatel; u karty
   s pausalem bez podilu - FSL, pausaly kancelari FM - nula).
2. Energie a sluzby v najmu - nefakturovane podily ostatnich najemcu
   (bez pausalu; typicky KJO v roce 2026).
3. Volne plochy - vsechny radky Karty pronajimatele (Areal.landlord):
   neobsazene prostory a vlastni kancelar.
4. Sluzby za pevnou cenu - polozky bez podilu, jen s pevnymi castkami
   (internet, srazkove vody Dle vymery): naklad, co se vybralo, vysledek.
5. Nerozuctovany zbytek - naklad polozky, ktery nepokryly podily ani
   pevne castky odectene z nakladu (ztraty bez klice, polozka bez klicu),
   zaporny = prebytek (napr. pausaly odectene nad naklad).

Pronajimatel celkem = podil pausalnich - pausaly + v najmu + volne plochy
+ (naklad - vybrano u sluzeb za pevnou cenu) + nerozuctovano. Plati:
celkem = naklad faktur - co zaplati najemci (overeno na NJ 08/2026).
"""
from collections import defaultdict
from decimal import Decimal

from core.models import BillingLine, CostEntry, InvoiceClassColor, Period, ServicePoolItem

NULA = Decimal("0")


def _d(hodnota):
    return Decimal(hodnota) if hodnota not in (None, "") else NULA


def obdobi_arealu(site, period):
    """Rozpad nakladu pronajimatele za jedno obdobi a areal."""
    lines = list(
        BillingLine.objects.filter(period=period, service_item__site=site)
        .select_related("service_item", "client_card__client")
    )
    landlord_id = site.landlord_id

    # Sluzby za pevnou cenu: polozka bez jedineho podilu (vsechny radky
    # bez share) - internet, srazkove vody. Nejsou to pausaly za energie,
    # maji vlastni blok.
    po_polozce = defaultdict(list)
    for l in lines:
        po_polozce[l.service_item_id].append(l)
    pevne = {
        item_id for item_id, radky in po_polozce.items()
        if all(r.share is None for r in radky) and not radky[0].service_item.pausal_tridy
    }
    sluzby = []
    for item_id in pevne:
        radky = po_polozce[item_id]
        naklad = _d((radky[0].calc_detail or {}).get("total_cost"))
        vybrano = sum((r.amount for r in radky if r.is_billed and r.client_card.client_id != landlord_id), NULA)
        sluzby.append({"item": radky[0].service_item, "naklad": naklad, "vybrano": vybrano,
                       "vysledek": vybrano - naklad})
    sluzby.sort(key=lambda s: s["vysledek"])
    lines = [l for l in lines if l.service_item_id not in pevne]

    nefakt = {(l.client_card_id, l.service_item_id) for l in lines if not l.is_billed}
    # pausaly po karte a Tride = fakturovana pevna castka, ktera se
    # neodecetla z nakladu. Obdobi spocitana pred ulozenim "fixed_odecteno"
    # to nevi - tam jen pevna castka vedle nefakturovaneho podilu.
    pausaly = defaultdict(lambda: defaultdict(lambda: NULA))
    for l in lines:
        if not l.is_billed or l.client_card.client_id == landlord_id:
            continue
        cd = l.calc_detail or {}
        if l.service_item.pausal_tridy:
            castka = l.amount
        elif "fixed_odecteno" in cd:
            castka = _d(cd.get("fixed_amount")) - _d(cd.get("fixed_odecteno"))
        elif (l.client_card_id, l.service_item_id) in nefakt:
            castka = _d(cd.get("fixed_amount"))
        else:
            continue
        if castka:
            pausaly[l.client_card_id][l.service_item.invoice_class] += castka

    karty = {}
    volne = defaultdict(lambda: NULA)
    for l in lines:
        cls = l.service_item.invoice_class
        if l.client_card.client_id == landlord_id:
            volne[cls] += l.amount
            continue
        if l.is_billed:
            continue
        k = karty.setdefault(l.client_card_id, {
            "card": l.client_card, "podil": defaultdict(lambda: NULA),
        })
        k["podil"][cls] += l.amount

    pausalni, v_najmu = [], []
    for card_id, k in karty.items():
        if card_id in pausaly:
            k["pausal"] = pausaly[card_id]
            pausalni.append(k)
        else:
            v_najmu.append(k)
    # karta s pausalem bez jedineho nefakturovaneho radku (FSL, EVUM - jen
    # pausal bez podilu) - v bloku 1 s podilem 0, at je pausal videt
    for card_id, po_tridach in pausaly.items():
        if card_id not in karty:
            card = next(l.client_card for l in lines if l.client_card_id == card_id)
            pausalni.append({"card": card, "podil": defaultdict(lambda: NULA), "pausal": po_tridach})

    # nerozuctovany zbytek po polozkach
    zbytek = []
    # Polozka s platnymi klici, ale bez jedineho radku = obdobi se pro ni
    # nepocitalo (NJ 01-05/2026). Neni to naklad pronajimatele, jen se to
    # ukaze zvlast, do souctu nejde.
    nespocitano = []
    for item in ServicePoolItem.objects.filter(site=site).exclude(id__in=pevne):
        radky = po_polozce.get(item.id, [])
        if radky:
            cd = radky[0].calc_detail or {}
            naklad = _d(cd.get("total_cost"))
            pokryto = NULA
            ma_odecteno = all("fixed_odecteno" in (r.calc_detail or {}) for r in radky)
            for r in radky:
                rcd = r.calc_detail or {}
                pokryto += r.amount - _d(rcd.get("fixed_amount"))
                if ma_odecteno:
                    pokryto += _d(rcd.get("fixed_odecteno"))
            if not ma_odecteno and "cena_z_faktury" not in cd:
                # starsi vypocet bez ulozeneho odectu - odhad z remaining_cost
                pokryto += max(naklad - _d(cd.get("remaining_cost")), NULA)
        else:
            t = CostEntry.totals_for(item, period)
            naklad = t["czk"] if t["czk"] is not None else (
                item.default_amount_czk if item.default_amount_czk is not None else NULA)
            pokryto = NULA
            if naklad and any(k.is_valid_for_period(period) for k in item.allocation_keys.all()):
                nespocitano.append({"item": item, "naklad": naklad})
                continue
        rozdil = (naklad - pokryto).quantize(Decimal("0.01"))
        if abs(rozdil) >= Decimal("0.5"):
            zbytek.append({"item": item, "naklad": naklad, "pokryto": pokryto, "zbytek": rozdil,
                           "cls": item.invoice_class})

    def soucet(radky, klic):
        return sum((sum(r[klic].values(), NULA) for r in radky), NULA)

    for r in pausalni:
        r["podil_celkem"] = sum(r["podil"].values(), NULA)
        r["pausal_celkem"] = sum(r["pausal"].values(), NULA)
        r["rozdil"] = r["pausal_celkem"] - r["podil_celkem"]
    for r in v_najmu:
        r["podil_celkem"] = sum(r["podil"].values(), NULA)
        # najem karty za obdobi - pro srovnani, energie a sluzby jsou v nem
        r["najem"] = r["card"].rent_for_period(period) or NULA
        r["rozdil"] = r["najem"] - r["podil_celkem"]
    pausalni.sort(key=lambda r: r["rozdil"])
    v_najmu.sort(key=lambda r: -r["podil_celkem"])

    b1_podil = soucet(pausalni, "podil")
    b1_pausal = soucet(pausalni, "pausal")
    b2 = soucet(v_najmu, "podil")
    b3 = sum(volne.values(), NULA)
    b4 = sum((z["zbytek"] for z in zbytek), NULA)
    b5 = -sum((s["vysledek"] for s in sluzby), NULA)
    return {
        "period": period,
        "spocitano": bool(lines),
        "pausalni": pausalni, "v_najmu": v_najmu, "volne": dict(volne), "zbytek": zbytek,
        "sluzby": sluzby, "nespocitano": nespocitano,
        "b1_podil": b1_podil, "b1_pausal": b1_pausal, "b1_rozdil": b1_pausal - b1_podil,
        "b2": b2, "b3": b3, "b4": b4, "b5": b5,
        "celkem": b1_podil - b1_pausal + b2 + b3 + b4 + b5,
    }


def rozsah_arealu(site, periods):
    """Vybrana obdobi s rozpadem + soucet za rozsah (a pausaly po kartach
    za rozsah - napr. cela topna sezona, at je videt, jestli je pausal
    ztratovy)."""
    obdobi = []
    for p in periods:
        o = obdobi_arealu(site, p)
        if o["spocitano"] or o["zbytek"] or o["nespocitano"]:
            obdobi.append(o)
    # sloupce jen pro Tridy, ktere se v roce opravdu objevi
    pouzite = set()
    for o in obdobi:
        pouzite |= set(o["volne"])
        for r in o["pausalni"] + o["v_najmu"]:
            pouzite |= {k for k, v in r["podil"].items() if v} | {k for k, v in (r.get("pausal") or {}).items() if v}
    tridy = [{"key": c, "label": l} for c, l in InvoiceClassColor.choices() if c in pouzite]
    for o in obdobi:
        for skupina in ("pausalni", "v_najmu"):
            for r in o[skupina]:
                r["bunky"] = [
                    {"podil": r["podil"].get(t["key"]), "pausal": (r.get("pausal") or {}).get(t["key"])}
                    for t in tridy
                ]
        o["volne_bunky"] = [o["volne"].get(t["key"]) for t in tridy]

    celkem = {k: sum((o[k] for o in obdobi), NULA)
              for k in ("b1_podil", "b1_pausal", "b1_rozdil", "b2", "b3", "b4", "b5", "celkem")}

    # pausaly za rok po kartach - zimni ztrata na teple se srovna s letnim ziskem
    po_karte = {}
    for o in obdobi:
        for r in o["pausalni"]:
            z = po_karte.setdefault(r["card"].id, {"card": r["card"], "podil": NULA, "pausal": NULA,
                                                   "mesicu": 0, "tridy": defaultdict(lambda: [NULA, NULA])})
            z["podil"] += r["podil_celkem"]; z["pausal"] += r["pausal_celkem"]; z["mesicu"] += 1
            for t in tridy:
                z["tridy"][t["key"]][0] += r["podil"].get(t["key"], NULA)
                z["tridy"][t["key"]][1] += (r.get("pausal") or {}).get(t["key"], NULA)
    rocne = []
    for z in po_karte.values():
        z["rozdil"] = z["pausal"] - z["podil"]
        z["bunky"] = [{"podil": z["tridy"][t["key"]][0] or None, "pausal": z["tridy"][t["key"]][1] or None}
                      for t in tridy]
        rocne.append(z)
    rocne.sort(key=lambda z: z["rozdil"])
    return {"obdobi": obdobi, "celkem": celkem, "rocne": rocne, "tridy": tridy}
