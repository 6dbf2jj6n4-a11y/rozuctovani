"""
Klient pro verejne ARES REST API (ares.gov.cz) - zakladni udaje o firme
a vypis z verejneho rejstriku (soud/oddil/vlozka). Pouziva se serverove
(napr. v management prikazu doplnit_ares) - pro klientske pouziti v
adminu viz core/static/core/js/ares_lookup.js, ktery dela totez primo
z prohlizece (tam CORS ARES povoluje, na rozdil od Registru DPH).
"""
import json
import urllib.error
import urllib.request

BASIC_URL = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/{ico}"
VR_URL = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr/{ico}"
RZP_URL = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-rzp/{ico}"

# pravniForma "101" = fyzicka osoba podnikajici dle zivnostenskeho zakona
# (OSVC) - ta neni v obchodnim rejstriku (VR), ale v zivnostenskem (RZP).
PRAVNI_FORMA_OSVC = "101"

# ARES vraci soud jen jako zkratku (napr. "KSOS") - obchodni rejstrik v CR
# vede jen techto 8 soudu, mapa je tedy uzavrena a stabilni.
COURT_NAMES = {
    "MSPH": "Městský soud v Praze",
    "KSPH": "Krajský soud v Praze",
    "KSCB": "Krajský soud v Českých Budějovicích",
    "KSPL": "Krajský soud v Plzni",
    "KSUL": "Krajský soud v Ústí nad Labem",
    "KSHK": "Krajský soud v Hradci Králové",
    "KSBR": "Krajský soud v Brně",
    "KSOS": "Krajský soud v Ostravě",
}


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def lookup_company(ico):
    """Vrati dict {name, dic, street, street_number, zip_code, city,
    insolvence_stav} nebo None.

    insolvence_stav je primo prevzaty priznak z ARES
    (seznamRegistraci.stavZdrojeIr - "Ir" = Insolvencni rejstrik):
    "AKTIVNI" (aktivni insolvencni rizeni), "HISTORICKY" (drive melo,
    uz uzavreno), "NEEXISTUJICI" (nikdy) nebo None (nezname). Oficialni
    verejna webova sluzba insolvencniho rejstriku (isir.justice.cz) je
    jen log/replikacni mechanismus (cely historicky zurnal udalosti k
    prehrani), ne jednoduchy dotaz podle ICO - tohle pole v ARES je
    nejjednodussi spolehlivy zdroj stejne informace, overeno na realnem
    pripadu (OKD, a.s., ICO 26863154 -> "AKTIVNI").
    """
    data = _get_json(BASIC_URL.format(ico=ico))
    if not data:
        return None
    result = {
        "name": data.get("obchodniJmeno") or "",
        "dic": data.get("dic") or "",
        "insolvence_stav": (data.get("seznamRegistraci") or {}).get("stavZdrojeIr"),
        "pravni_forma": data.get("pravniForma") or "",
    }
    sidlo = data.get("sidlo") or {}
    result["street"] = sidlo.get("nazevUlice") or sidlo.get("nazevObce") or ""
    cislo = sidlo.get("cisloDomovni")
    cislo_str = str(cislo) if cislo else ""
    orientacni = sidlo.get("cisloOrientacni")
    if orientacni:
        cislo_str = f"{cislo_str}/{orientacni}"
    result["street_number"] = cislo_str
    psc = sidlo.get("psc")
    result["zip_code"] = str(psc) if psc else ""
    result["city"] = sidlo.get("nazevObce") or ""
    return result


def lookup_registry(ico):
    """Vrati dict {court, section, insert} (court uz rozepsany na plny nazev) nebo None."""
    data = _get_json(VR_URL.format(ico=ico))
    if not data:
        return None
    zaznamy = data.get("zaznamy") or []
    if not zaznamy:
        return None
    spisove_znacky = zaznamy[0].get("spisovaZnacka") or []
    if not spisove_znacky:
        return None
    sz = spisove_znacky[0]
    soud_code = sz.get("soud")
    vlozka = sz.get("vlozka")
    return {
        "court": COURT_NAMES.get(soud_code, soud_code or ""),
        "section": sz.get("oddil") or "",
        "insert": str(vlozka) if vlozka else "",
    }


def lookup_trade_register(ico):
    """Vrati dict {zivnosti_aktivni, zivnosti_zanikle, provozovny_aktivni,
    provozovny_zanikle, obory} nebo None - protejsek k lookup_registry(),
    ale pro zivnostensky rejstrik (RZP), kde jsou fyzicke osoby (OSVC),
    ktere v obchodnim rejstriku (VR) vubec nejsou.

    Cistě informativni signal (napr. 0 aktivnich provozoven) - NENI to
    samo o sobe rizikovy priznak jako "v likvidaci"/insolvence, spousta
    OSVC legitimne podnika bez registrovane provozovny.
    """
    data = _get_json(RZP_URL.format(ico=ico))
    if not data:
        return None
    zaznamy = data.get("zaznamy") or []
    if not zaznamy:
        return None
    z = zaznamy[0]
    zivnosti_stav = z.get("zivnostiStav") or {}
    provozovny_stav = z.get("provozovnyStav") or {}
    aktivni_obory = [
        zivnost.get("predmetPodnikani")
        for zivnost in (z.get("zivnosti") or [])
        if not zivnost.get("datumZaniku") and zivnost.get("predmetPodnikani")
    ]
    return {
        "zivnosti_aktivni": zivnosti_stav.get("pocetAktivnich"),
        "zivnosti_zanikle": zivnosti_stav.get("pocetZaniklych"),
        "provozovny_aktivni": provozovny_stav.get("pocetAktivnich"),
        "provozovny_zanikle": provozovny_stav.get("pocetZaniklych"),
        "obory": aktivni_obory,
    }
