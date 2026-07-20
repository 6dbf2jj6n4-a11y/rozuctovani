"""
Registr platcu DPH (Financni sprava CR) - overeni spolehlivosti platce
a zverejnenych bankovnich uctu podle DIC/ICO.

Jde o SOAP API (ne REST jako ARES), nejde volat primo z prohlizece
(server nema CORS pro cizi originy) - proto se vola odtud, ze serveru,
a vysledek se klientovi vraci uz jako JSON pres vlastni admin endpoint.

Overeno na realnem DIC CALAMARI SE (28940423) - vraci zverejneny ucet
261241857/0300, coz odpovida udaji v sablone smlouvy.
"""
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

SOAP_URL = "https://adisrws.mfcr.cz/dpr/axis2/services/rozhraniCRPDPH.rozhraniCRPDPHSOAP"
NS = "http://adis.mfcr.cz/rozhraniCRPDPH/"

# Male, stabilni mapovani nejcastejsich kodu bank v CR (kod prideluje CNB,
# meni se jen vyjimecne) - jen pro pohodli, neni to autoritativni zdroj.
BANK_CODE_NAMES = {
    "0100": "Komerční banka",
    "0300": "ČSOB",
    "0600": "MONETA Money Bank",
    "0800": "Česká spořitelna",
    "2010": "Fio banka",
    "2020": "MUFG Bank",
    "2060": "Citfin",
    "2070": "TRINITY BANK",
    "2100": "Hypoteční banka",
    "2200": "Peněžní dům",
    "2220": "Artesa",
    "2250": "Banka CREDITAS",
    "2260": "NEY spořitelní družstvo",
    "2600": "Citibank Europe",
    "2700": "UniCredit Bank",
    "3030": "Air Bank",
    "3050": "BNP Paribas",
    "3060": "PKO BP",
    "3500": "ING Bank",
    "4000": "Expobank",
    "5500": "Raiffeisenbank",
    "5800": "J&T Banka",
    "6000": "PPF banka",
    "6100": "Equa bank",
    "6200": "COMMERZBANK",
    "6210": "mBank",
    "6300": "GE Money Bank",
    "6700": "Všeobecná úverová banka",
    "6800": "Sberbank CZ",
    "7910": "Deutsche Bank",
    "7940": "Waldviertler Sparkasse",
    "8030": "Volksbank",
    "8040": "Oberbank",
    "8060": "Stavební spořitelna České spořitelny",
    "8090": "Česká exportní banka",
    "8150": "HSBC Continental Europe",
    "8200": "PRIVAT BANK",
    "8220": "Payment execution",
    "8230": "EEPFinance",
    "8240": "Poštová banka",
    "8250": "Bank of China",
    "8265": "Bank of Communications",
    "8270": "Community Federal Savings Bank",
    "8280": "B-Efekt",
}


def lookup_vat_payer(ico_or_dic, timeout=15):
    """Vrati dict {dic, nespolehlivy_platce, nazev, accounts: [{cislo_uctu, kod_banky,
    nazev_banky}]}, nebo None pokud DIC neni v registru (napr. neni platce DPH)."""
    dic_digits = re.sub(r"\D", "", ico_or_dic or "")
    if not dic_digits:
        return None

    envelope = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        f'<StatusNespolehlivyPlatceRozsirenyRequest xmlns="{NS}">'
        f"<dic>{dic_digits}</dic>"
        "</StatusNespolehlivyPlatceRozsirenyRequest>"
        "</soap:Body></soap:Envelope>"
    )
    req = urllib.request.Request(
        SOAP_URL,
        data=envelope.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f"{NS}getStatusNespolehlivyPlatceRozsireny",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except (urllib.error.URLError, TimeoutError):
        return None

    root = ET.fromstring(body)
    ns = {"a": NS}
    subjekt = root.find(".//a:statusPlatceDPH", ns)
    if subjekt is None:
        return None

    accounts = []
    for ucet in subjekt.findall(".//a:zverejneneUcty/a:ucet", ns):
        std = ucet.find("a:standardniUcet", ns)
        if std is None:
            continue
        prefix = std.get("predcisli")
        cislo = std.get("cislo")
        kod = std.get("kodBanky")
        accounts.append({
            "cislo_uctu": f"{prefix}-{cislo}" if prefix else cislo,
            "kod_banky": kod,
            "nazev_banky": BANK_CODE_NAMES.get(kod, ""),
        })

    nazev_el = subjekt.find("a:nazevSubjektu", ns)

    return {
        "dic": subjekt.get("dic"),
        "nespolehlivy_platce": subjekt.get("nespolehlivyPlatce"),
        "nazev": (nazev_el.text or "").strip() if nazev_el is not None else "",
        "accounts": accounts,
    }
