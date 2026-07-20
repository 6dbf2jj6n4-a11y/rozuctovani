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
    """Vrati dict {name, dic, street, street_number, zip_code, city} nebo None."""
    data = _get_json(BASIC_URL.format(ico=ico))
    if not data:
        return None
    result = {
        "name": data.get("obchodniJmeno") or "",
        "dic": data.get("dic") or "",
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
