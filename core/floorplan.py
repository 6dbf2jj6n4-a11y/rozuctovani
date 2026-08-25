"""Cteni planku (2D pudorysu) ulozenych jako SVG a jejich spojeni
s Pronajimanymi prostory.

Kontrakt s vykresem (viz ~/Desktop/RenteX/plany/README.md):

* vrstva ``podklad``          - kresba z vykresu, nesaha se do ni
* vrstva ``Plochy_rentex``    - polygony pronajimanych prostor,
                                ``id`` = ``Unit.name`` s podtrzitkem
                                misto mezery (``AB 3.03`` -> ``AB_3.03``)
* vrstva ``Plochy_spolecne``  - spolecne prostory (chodby, WC, kuchynka),
                                ``id`` nema vyznam

V databazi se z planku neuklada NIC krome samotneho souboru - tvary zustavaji
ve vykresu, obsazenost v Kartach. Parovani je jen pres to ``id``.
"""
import re
from xml.etree import ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"

VRSTVA_PRONAJIMANE = "Plochy_rentex"
VRSTVA_SPOLECNE = "Plochy_spolecne"

# Vrstvy se v Inkscapu pojmenovavaji rucne, takze se snadno prohodi poradi
# slov nebo velikost pismen ("rentex_plochy" misto "Plochy_rentex"). Radeji
# prijmeme obe podoby, nez aby se planek tise nevykreslil. Viz Daniel
# 2026-08-24 (dv_1NP.svg).
ALIASY_VRSTEV = {
    VRSTVA_PRONAJIMANE: ("plochy_rentex", "rentex_plochy"),
    VRSTVA_SPOLECNE: ("plochy_spolecne", "spolecne_plochy"),
}

# tvary, ktere ve vrstvach ploch davaji smysl
TVARY = ("rect", "path", "polygon", "circle", "ellipse")


def id_na_nazev(sifra):
    """``AB_3.03`` -> ``AB 3.03`` (podtrzitko zastupuje mezeru, protoze
    XML id mezeru obsahovat nesmi)."""
    return sifra.replace("_", " ")


def nazev_na_id(nazev):
    """Opacny smer k :func:`id_na_nazev`."""
    return nazev.replace(" ", "_")


def _bez_ns(tag):
    return tag.split("}", 1)[-1]


def _vrstvy(korenovy_prvek):
    """Vrati {nazev vrstvy: prvek} pro vrstvy nejvyssi urovne.

    Vrstva pojmenovana nekterym z ALIASU se zaroven zpristupni pod svym
    ocekavanym nazvem, takze "rentex_plochy" funguje stejne jako
    "Plochy_rentex"."""
    out = {}
    for g in korenovy_prvek.findall("{%s}g" % SVG_NS):
        if g.get("{%s}groupmode" % INKSCAPE_NS) != "layer":
            continue
        nazev = g.get("{%s}label" % INKSCAPE_NS)
        if not nazev:
            continue
        out[nazev] = g
        for ocekavany, aliasy in ALIASY_VRSTEV.items():
            if nazev.lower() in aliasy and ocekavany not in out:
                out[ocekavany] = g
    return out


def kody_ploch(svg_text):
    """Vrati (pronajimane, spolecne) - seznamy ``id`` tvaru v obou vrstvach.

    Pronajimane jsou uz prevedene na nazvy Prostor (``AB 3.03``), spolecne
    zustavaji tak, jak jsou ve vykresu.
    """
    koren = ET.fromstring(svg_text)
    vrstvy = _vrstvy(koren)

    def _ids(nazev_vrstvy):
        vrstva = vrstvy.get(nazev_vrstvy)
        if vrstva is None:
            return []
        return [
            prvek.get("id")
            for prvek in vrstva
            if _bez_ns(prvek.tag) in TVARY and prvek.get("id")
        ]

    return (
        [id_na_nazev(x) for x in _ids(VRSTVA_PRONAJIMANE)],
        _ids(VRSTVA_SPOLECNE),
    )


def _nahrad_stav_stylu(prvek):
    """Odstrani z tvaru inline vypln a tah, aby o barve rozhodovalo CSS.

    Barvy, ktere si Daniel nastavil pri kresleni v Inkscapu, slouzi jen
    jemu - v aplikaci se plocha barvi podle obsazenosti.
    """
    styl = prvek.get("style") or ""
    zbytek = [
        kus for kus in styl.split(";")
        if kus.strip() and not kus.strip().startswith(("fill", "stroke"))
    ]
    if zbytek:
        prvek.set("style", ";".join(zbytek))
    else:
        prvek.attrib.pop("style", None)
    for atribut in ("fill", "stroke", "fill-opacity", "stroke-width"):
        prvek.attrib.pop(atribut, None)


def _matice(prvek):
    """Transformace tvaru jako sestice (a, b, c, d, e, f).

    Tvar muze mit vlastni `transform` - napr. plany prevedene z PDF maji
    na kazde ceste matici, ktera prevraci osu y. Bez ni vyjde stred
    zrcadlove a popisek skonci mimo vykres. Viz Daniel 2026-08-25
    (podklad_NJ_haly_2NP)."""
    shoda = re.search(r"matrix\(([^)]*)\)", prvek.get("transform") or "")
    if not shoda:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    try:
        cisla = [float(v) for v in re.split(r"[,\s]+", shoda.group(1).strip())]
        return tuple(cisla) if len(cisla) == 6 else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    except ValueError:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _stred_tvaru(prvek):
    """Přibližný střed tvaru v souřadnicích výkresu, nebo None.

    U obdélníku je to skutečný střed, u cesty průměr vrcholů - pro naše
    plochy (obdélníky a zalomená „el“) leží uvnitř, což na popisek stačí.
    """
    druh = _bez_ns(prvek.tag)
    if druh == "rect":
        try:
            a, b, c, d, e, f = _matice(prvek)
            x = float(prvek.get("x", 0)) + float(prvek.get("width", 0)) / 2
            y = float(prvek.get("y", 0)) + float(prvek.get("height", 0)) / 2
            vyska = abs(float(prvek.get("height", 0)) * d)
            sirka = abs(float(prvek.get("width", 0)) * a)
            return (a * x + c * y + e, b * x + d * y + f, vyska, sirka)
        except (TypeError, ValueError):
            return None
    if druh in ("path", "polygon"):
        souradnice = prvek.get("d") or prvek.get("points") or ""
        # transformace se predava dal, jinak by se stred pocital
        # v netransformovane soustave
        tag = '<path d="%s" transform="%s"/>' % (souradnice, prvek.get("transform") or "")
        body = _body_cesty(tag) if druh == "path" else []
        if druh == "polygon":
            cisla = [float(v) for v in re.findall(r"-?\d+\.?\d*", souradnice)]
            body = list(zip(cisla[0::2], cisla[1::2]))
        if not body:
            return None
        xs = [b[0] for b in body]
        ys = [b[1] for b in body]
        return (sum(xs) / len(xs), sum(ys) / len(ys),
                max(ys) - min(ys), max(xs) - min(xs))
    return None


def _rozsah_velikosti(koren):
    """Meze velikosti popisku V JEDNOTKACH KRESBY podle meritka vykresu.

    Planky nemaji spolecne meritko: NJ vykres je siroky ~865 jednotek,
    DV ~1564. Oba se pritom na strance vykresluji na stejnou sirku, takze
    pevne meze v jednotkach kresby vysly na NJ citelne a na DV skoro
    dvakrat drobneji - presne to Daniel 2026-08-25 hlasil. Meze se proto
    odvozuji od sirky vykresu, aby popisek vysel na obrazovce vzdycky
    stejne velky.

    Koeficienty jsou nastavene tak, aby NJ planky zustaly PRESNE jak jsou
    (9 az 16 jednotek pri sirce 865) - tam uz je vysledek schvaleny.
    """
    sirka = None
    ramec = (koren.get("viewBox") or "").split()
    if len(ramec) == 4:
        try:
            sirka = float(ramec[2])
        except ValueError:
            sirka = None
    if not sirka:
        # Nektere vykresy maji jen width (klidne i s jednotkou, "230mm").
        try:
            sirka = float(re.sub(r"[^\d.]", "", koren.get("width") or "") or 0)
        except ValueError:
            sirka = None
    if not sirka:
        sirka = 865.0        # nouzove: rozmer NJ planku
    return sirka * 0.0104, sirka * 0.0185


def _popisek(prvek, text, trida, meze, radek=1):
    """Vytvoří <text> pod středem tvaru. `radek` posouvá pod sebe."""
    stred = _stred_tvaru(prvek)
    if not stred:
        return None
    x, y, vyska, sirka = stred
    # Delitel zvetsen (bylo vyska/6) a meze uz nejsou pevne, ale podle
    # meritka vykresu - viz _rozsah_velikosti. Daniel 2026-08-25.
    dolni, horni = meze
    velikost = max(dolni, min(horni, vyska / 5))
    # Delsi nazev klienta se do uzke plochy nevejde a pretece pres
    # sousedni - zuzime ho podle sirky tvaru. 0,6 je priblizna sirka
    # znaku vuci vysce pisma u bezpatkoveho fontu.
    if sirka and text:
        velikost = max(dolni, min(velikost, sirka / (len(text) * 0.6)))
    popisek = ET.Element("{%s}text" % SVG_NS)
    popisek.set("x", "%.1f" % x)
    # pod číslo místnosti z podkladu, ne přes něj
    popisek.set("y", "%.1f" % (y + velikost * (0.5 + radek)))
    popisek.set("class", trida)
    popisek.set("font-size", "%.1f" % velikost)
    popisek.text = text
    return popisek


def oznac_plochy(svg_text, stavy):
    """Vrati SVG pripravene k vlozeni do stranky.

    ``stavy`` je {nazev Prostoru: dict}, kde dict nese aspon klic ``stav``
    (retezec pouzity jako CSS trida) a volitelne ``popis`` do tooltipu a
    ``odkaz`` na Kartu. Prostory, ktere ve ``stavy`` nejsou, dostanou stav
    ``neprirazeno``.
    """
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("inkscape", INKSCAPE_NS)
    ET.register_namespace("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd")
    koren = ET.fromstring(svg_text)
    vrstvy = _vrstvy(koren)

    vrstva = vrstvy.get(VRSTVA_PRONAJIMANE)
    if vrstva is not None:
        meze = _rozsah_velikosti(koren)
        popisky = []
        for prvek in vrstva:
            if _bez_ns(prvek.tag) not in TVARY or not prvek.get("id"):
                continue
            nazev = id_na_nazev(prvek.get("id"))
            udaje = stavy.get(nazev) or {"stav": "neprirazeno"}
            _nahrad_stav_stylu(prvek)
            prvek.set("class", "rx-plocha rx-%s" % udaje["stav"])
            prvek.set("data-kod", nazev)
            if udaje.get("popis"):
                prvek.set("data-popis", udaje["popis"])
            if udaje.get("odkaz"):
                prvek.set("data-odkaz", udaje["odkaz"])

            kod = udaje.get("kod_klienta")
            if kod:
                popisek = _popisek(prvek, kod, "rx-kod-klienta", meze)
                if popisek is not None:
                    popisky.append(popisek)
            budouci_kod = udaje.get("budouci_kod")
            if budouci_kod:
                popisek = _popisek(prvek, "→ " + budouci_kod, "rx-kod-budouci", meze, radek=2)
                if popisek is not None:
                    popisky.append(popisek)
        # až po tvarech, aby se popisky kreslily navrch
        for popisek in popisky:
            vrstva.append(popisek)

    vrstva = vrstvy.get(VRSTVA_SPOLECNE)
    if vrstva is not None:
        for prvek in vrstva:
            if _bez_ns(prvek.tag) not in TVARY:
                continue
            _nahrad_stav_stylu(prvek)
            prvek.set("class", "rx-plocha rx-spolecne")

    xml = ET.tostring(koren, encoding="unicode")
    # ElementTree pise deklaraci namespace i tam, kde uz je - neskodne,
    # ale ubira na citelnosti vystupu ve zdrojaku stranky
    return re.sub(r'\s+xmlns:ns\d+="[^"]*"', "", xml)


# ------------------------------------------------------------------ zmenseni

#: na kolik desetinnych mist se krati souradnice cest
DESETINNA_MISTA = 1

_VZOR_CESTA = re.compile(r'(<path\b[^>]*?)\sd="([^"]*)"', re.S)
_VZOR_CISLO = re.compile(r"-?\d+\.\d+")


def _body_cesty(tag):
    """Koncove body cesty v souradnicich dokumentu (vcetne transformace)."""
    d = re.search(r'\sd="([^"]*)"', tag)
    if not d:
        return []
    tr = re.search(r'transform="matrix\(([^)]*)\)"', tag)
    if tr:
        a, b, c, dd, e, f = [float(v) for v in re.split(r"[,\s]+", tr.group(1).strip())]
    else:
        a, b, c, dd, e, f = 1, 0, 0, 1, 0, 0

    toks = re.findall(r"[MmLlHhVvCcZz]|-?\d*\.?\d+(?:e-?\d+)?", d.group(1))
    x = y = 0.0
    cmd = None
    i = 0
    pts = []
    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            continue
        try:
            if cmd in "MmLl":
                dx, dy = float(toks[i]), float(toks[i + 1])
                i += 2
                x, y = (x + dx, y + dy) if cmd in "ml" else (dx, dy)
                cmd = "l" if cmd == "m" else ("L" if cmd == "M" else cmd)
            elif cmd in "Hh":
                dx = float(toks[i]); i += 1
                x = x + dx if cmd == "h" else dx
            elif cmd in "Vv":
                dy = float(toks[i]); i += 1
                y = y + dy if cmd == "v" else dy
            elif cmd in "Cc":
                v = [float(toks[i + k]) for k in range(6)]; i += 6
                x, y = (x + v[4], y + v[5]) if cmd == "c" else (v[4], v[5])
            else:
                i += 1
                continue
        except (IndexError, ValueError):
            i += 1
            continue
        pts.append((a * x + c * y + e, b * x + dd * y + f))
    return pts


def zmensi(svg_text, mist=DESETINNA_MISTA, rezerva=2.0):
    """Vyhodi z vykresu balast po exportu z CADu a zkrati souradnice.

    Vraci (novy_text, prehled). Delaji se dve veci:

    1. **Smazou se tvary uplne mimo vykres** - ram listu A3, znacky pro
       skladani a registracni znacky mimo list. V oriznutem pohledu je
       nevidis, jen nafukuji soubor a rozhazuji vyber pres Ctrl+A.
    2. **Zkrati se souradnice cest.** CAD pise pet desetinnych mist,
       pritom jedna jednotka odpovida na vytistene A4 asi 0,064 mm - paté
       desetinne misto je tedy sest desetimiliontin milimetru. Na jedno
       desetinne misto vyjde krok 0,006 mm, porad o rad jemneji, nez
       rozlisi tiskarna. **Na nulu desetinnych mist nechodit** - kotovaci
       cisla jsou vektorove obrysy a zacnou se drolit.

    Tvary ploch (rect/polygon ve vrstvach Plochy_*) se nedotýka, aby se
    nemohlo stat, ze se rozejdou s `id`.
    """
    vb = re.search(r'viewBox="([^"]*)"', svg_text)
    smazano = 0
    if vb:
        x0, y0, w, h = [float(v) for v in vb.group(1).split()]
        x1, y1 = x0 + w, y0 + h
        ke_smazani = []
        for m in re.finditer(r"<path\b[^>]*?/>", svg_text, re.S):
            pts = _body_cesty(m.group(0))
            if pts and all(
                px < x0 - rezerva or px > x1 + rezerva or py < y0 - rezerva or py > y1 + rezerva
                for px, py in pts
            ):
                ke_smazani.append((m.start(), m.end()))
        for zacatek, konec in sorted(ke_smazani, key=lambda z: -z[0]):
            svg_text = svg_text[:zacatek] + svg_text[konec:]
        smazano = len(ke_smazani)

    puvodni = len(svg_text)

    def _cislo(m):
        out = "%.*f" % (mist, round(float(m.group(0)), mist))
        if "." in out:
            out = out.rstrip("0").rstrip(".")
        return "0" if out in ("", "-", "-0") else out

    # POZOR: jen atribut `d` u <path>. Sirsi vzor by sedl i na konec
    # `id="AB_3.10"` a udelal by z nej `AB_3.1`.
    novy = _VZOR_CESTA.sub(
        lambda m: '%s d="%s"' % (m.group(1), _VZOR_CISLO.sub(_cislo, m.group(2))), svg_text
    )

    return novy, {
        "smazano": smazano,
        "pred": puvodni,
        "po": len(novy),
        "usporeno": puvodni - len(novy),
    }


# -------------------------------------------------------------------- tisk

# Barvy pro tisk musi byt primo v atributech tvaru - svglib CSS neresi.
# Karta najemce je cernobila (viz core/client_card_generator.py), takze se
# rozlisuje jen sytosti sedi a silou obrysu. Vyplne jsou pruhledne, aby pod
# nimi zustala citelna cisla mistnosti a zdi z podkladu.
TISK_MOJE = {"fill": "#000000", "fill-opacity": "0.28", "stroke": "#000000", "stroke-width": "2.5"}
TISK_CIZI = {"fill": "#000000", "fill-opacity": "0.07", "stroke": "#808080", "stroke-width": "0.8"}
TISK_SPOLECNE = {"fill": "#000000", "fill-opacity": "0.04", "stroke": "#a0a0a0", "stroke-width": "0.6"}


def oznac_plochy_pro_tisk(svg_text, moje_kody):
    """SVG pripravene pro svglib -> reportlab (priloha Karty najemce).

    Plochy klienta se zvyrazni, ostatni pronajimatelne zesednou (klient
    nema videt, kdo sedi vedle) a spolecne zustanou jen naznacene.
    Na rozdil od :func:`oznac_plochy` se barvy zapisuji primo do atributu,
    protoze svglib nezna CSS ani tridy.
    """
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("inkscape", INKSCAPE_NS)
    ET.register_namespace("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd")
    koren = ET.fromstring(svg_text)
    vrstvy = _vrstvy(koren)
    moje = {nazev_na_id(k) for k in moje_kody}

    def _obarvi(prvek, barvy):
        _nahrad_stav_stylu(prvek)
        for atribut, hodnota in barvy.items():
            prvek.set(atribut, hodnota)

    vrstva = vrstvy.get(VRSTVA_PRONAJIMANE)
    if vrstva is not None:
        for prvek in vrstva:
            if _bez_ns(prvek.tag) not in TVARY or not prvek.get("id"):
                continue
            _obarvi(prvek, TISK_MOJE if prvek.get("id") in moje else TISK_CIZI)

    vrstva = vrstvy.get(VRSTVA_SPOLECNE)
    if vrstva is not None:
        for prvek in vrstva:
            if _bez_ns(prvek.tag) in TVARY:
                _obarvi(prvek, TISK_SPOLECNE)

    return ET.tostring(koren, encoding="unicode")


def planky_pro_kartu(card):
    """Vrati [(Planek, [nazvy ploch karty na nem])] pro Kartu klienta.

    Jen patra, kde karta opravdu neco ma - najemce jedne kancelare nema co
    delat s pudorysem haly D3.
    """
    from core.models import Floorplan

    moje = {cu.unit.name for cu in card.card_units.select_related("unit") if cu.unit}
    if not moje:
        return []

    out = []
    for plan in Floorplan.objects.filter(
        site__units__card_units__card=card, is_active=True
    ).distinct():
        try:
            pronajimane, _ = kody_ploch(plan.read_svg())
        except Exception:
            continue
        na_planku = sorted(moje & set(pronajimane))
        if na_planku:
            out.append((plan, na_planku))
    return out


# ---------------------------------------------------------------- obsazenost

#: kolik dni dopredu se konec najmu uz hlasi jako "konci"
DNI_DO_KONCE = 90


def stavy_ploch(site, k_datu, dni_do_konce=DNI_DO_KONCE):
    """Vrati {nazev Prostoru: {stav, popis, odkaz, klient}} pro cely areal.

    Stavy:

    ``obsazeno``     - plocha ma k datu platnou Kartu najemce
    ``konci``        - totez, ale Karta konci do ``dni_do_konce`` dni
    ``volne``        - plochu drzi Pronajimatel (prazdna, nepronajata)
    ``neprirazeno``  - plocha neni na zadne platne Karte; tohle nema
                       nastat a je to duvod k oprave dat

    Prostory bez Karty se do vysledku nedavaji - o stavu ``neprirazeno``
    rozhoduje az :func:`oznac_plochy` podle toho, ze je ve vykresu a tady
    chybi. Diky tomu se nemusi tahat vsechny Prostory arealu.
    """
    from datetime import timedelta

    from django.db.models import Q
    from django.urls import reverse

    from core.models import CardUnit

    radky = (
        CardUnit.objects.select_related("card", "card__client", "unit")
        .filter(
            unit__site=site,
            card__is_active=True,
            card__valid_from__lte=k_datu,
        )
        .filter(Q(card__valid_to__isnull=True) | Q(card__valid_to__gte=k_datu))
        .order_by("card__valid_from")
    )

    # Kdo plochu převezme AŽ POTOM. Bez toho plánek k dnešku mlčí o tom, že
    # je plocha od příštího měsíce slíbená - a člověk ji pak marně převádí.
    budouci = {}
    for cu in (
        CardUnit.objects.select_related("card", "card__client", "unit")
        .filter(unit__site=site, card__is_active=True, card__valid_from__gt=k_datu)
        .order_by("-card__valid_from")          # dřívější přepíše pozdější
    ):
        budouci[cu.unit.name] = cu.card

    hranice = k_datu + timedelta(days=dni_do_konce)
    out = {}
    for cu in radky:
        karta = cu.card
        klient = karta.client
        if klient.is_landlord:
            stav = "volne"
            popis = "Volné – drží pronajímatel"
        elif karta.valid_to and karta.valid_to <= hranice:
            stav = "konci"
            popis = "%s – končí %s" % (klient.name, karta.valid_to.strftime("%-d. %-m. %Y"))
        else:
            stav = "obsazeno"
            popis = klient.name
        # pozdejsi Karta prepise drivejsi (order_by vyse), takze u prekryvu
        # vyhrava ta, ktera zacala pozdeji
        prijde = budouci.get(cu.unit.name)
        if prijde:
            popis += " · od %s %s" % (
                prijde.valid_from.strftime("%-d. %-m. %Y"), prijde.client.name)

        out[cu.unit.name] = {
            "stav": stav,
            "popis": popis,
            "budouci_kod": (prijde.client.code or prijde.client.name[:10]) if prijde else "",
            "budouci_od": prijde.valid_from if prijde else None,
            "klient": klient.name,
            # kód se vypisuje přímo do plánku - celé jméno by se do kanceláře
            # nevešlo, kód je krátký a Daniel ho zná
            "kod_klienta": klient.code or klient.name[:10],
            "vymera": cu.area_m2,
            "odkaz": reverse("admin:core_clientcard_change", args=[karta.pk]),
        }
    return out


def kontrola_parovani(site):
    """Porovna plochy ve vykresech arealu proti Pronajimanym prostorum v DB.

    Vraci dict s klici ``plany`` (za kazdy planek seznam kodu bez Prostoru),
    ``bez_planku`` (Prostory arealu, ktere nejsou na zadnem planku) a
    ``chybne`` (planky, ktere se nepodarilo precist).
    """
    from core.models import Floorplan, Unit

    v_planech = set()
    plany = []
    chybne = []
    for plan in Floorplan.objects.filter(site=site, is_active=True):
        try:
            pronajimane, spolecne = kody_ploch(plan.read_svg())
        except Exception as chyba:            # poskozeny nebo jiny soubor
            chybne.append((plan, str(chyba)))
            continue
        v_planech.update(pronajimane)
        existujici = set(
            Unit.objects.filter(site=site, name__in=pronajimane).values_list("name", flat=True)
        )
        plany.append({
            "plan": plan,
            "pocet": len(pronajimane),
            "spolecnych": len(spolecne),
            "bez_prostoru": sorted(set(pronajimane) - existujici),
        })

    bez_planku = sorted(
        Unit.objects.filter(site=site)
        .exclude(name__in=v_planech)
        .values_list("name", flat=True)
    )
    return {"plany": plany, "bez_planku": bez_planku, "chybne": chybne}
