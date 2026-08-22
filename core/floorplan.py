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
    """Vrati {nazev vrstvy: prvek} pro vrstvy nejvyssi urovne."""
    out = {}
    for g in korenovy_prvek.findall("{%s}g" % SVG_NS):
        if g.get("{%s}groupmode" % INKSCAPE_NS) != "layer":
            continue
        nazev = g.get("{%s}label" % INKSCAPE_NS)
        if nazev:
            out[nazev] = g
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
        out[cu.unit.name] = {
            "stav": stav,
            "popis": popis,
            "klient": klient.name,
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
