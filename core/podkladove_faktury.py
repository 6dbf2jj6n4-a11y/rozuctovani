"""Podkladove faktury - propojeni prijatych faktur dodavatelu v ABRA Flexi
s polozkami a obdobimi, aby je klientsky portal mohl nabidnout ke stazeni.

Ktera faktura patri ke ktere polozce, urcuje stejne mapovani jako import
nakladu (core/management/commands/import_naklady_flexi.py - POPIS
"TRIDA MM/RRRR", MAPOVANI podle tridy + strediska + dodavatele). Naklady
samotne se tu nemeni - jde jen o odkaz na doklad.

PDF se nikam nekopiruje: zapise se jen id prilohy v ABRA a portal ji pri
stazeni streamuje (stahnout_prilohu). Viz core.models.PodkladovaFaktura.
"""
from core.flexi_client import FlexiClient
from core.management.commands.import_naklady_flexi import MAPOVANI, POPIS, Command as ImportNakladu
from core.models import Period, PodkladovaFaktura, ServicePoolItem


def _pdf_priloha(client, flexi_id):
    """(id, nazev souboru) prvni PDF prilohy faktury, nebo (None, "")."""
    data = client._request(
        "GET", client._evidence_url(f"faktura-prijata/{flexi_id}/prilohy"),
        params={"detail": "custom:id,nazSoub,contentType"},
    ) or {}
    prilohy = data.get("winstrom", {}).get("priloha", [])
    pdf = [p for p in prilohy if "pdf" in (p.get("contentType") or "").lower()
           or (p.get("nazSoub") or "").lower().endswith(".pdf")]
    vybrana = (pdf or prilohy or [None])[0]
    if vybrana is None:
        return None, ""
    return int(vybrana["id"]), vybrana.get("nazSoub") or ""


def propojit(od=(2026, 1), zapsat=False, client=None):
    """Projde prijate faktury v ABRA od obdobi `od` (rok, mesic) a pripoji
    je k polozkam a obdobim. Opakovatelne - existujici vazby jen
    aktualizuje (napr. kdyz se v ABRA vymenila priloha).

    Vraci (radky, nerozpoznane): radky = [(obdobi, polozka, kod, dodavatel,
    soubor, stav)], stav je "nova" / "beze zmeny" / "zmena" / "chybi obdobi".
    """
    client = client or FlexiClient()
    rozpad = ImportNakladu()._rozpad_faktury  # SMVAK NJ = voda + srazkove
    faktury = client.list_records(
        "faktura-prijata", f"datVyst>='{od[0]}-01-01'",
        extra_params={"limit": "0", "detail": "full"},
    )
    polozky = {p.name: p for p in ServicePoolItem.objects.all()}
    obdobi = {(p.year, p.month): p for p in Period.objects.all()}

    radky, nerozpoznane = [], []
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
        if (rok, do_m) < tuple(od):
            continue
        stred = (f.get("stredisko") or "").replace("code:", "").strip()
        firma = (f.get("firma") or "").replace("code:", "").strip()

        tridy = {cast for cast, _castka in rozpad(client, f, trida)}
        cile = []
        for cast in tridy:
            klic = (cast, stred, firma)
            if klic in MAPOVANI and MAPOVANI[klic][0] in polozky:
                cile.append(polozky[MAPOVANI[klic][0]])
            else:
                nerozpoznane.append((f.get("kod"), popis, cast, stred, firma))
        if not cile:
            continue

        priloha_id, soubor = _pdf_priloha(client, f["id"])
        dodavatel = f.get("nazFirmy") or (f.get("firma@showAs") or "").split(":", 1)[-1].strip()
        for polozka in cile:
            for mesic in range(od_m, do_m + 1):
                p = obdobi.get((rok, mesic))
                if p is None:
                    radky.append((f"{mesic:02d}/{rok}", polozka.name, f.get("kod"), dodavatel, soubor, "chybí období"))
                    continue
                hodnoty = {
                    "kod": f.get("kod") or "", "dodavatel": dodavatel[:200], "popis": popis[:200],
                    "priloha_id": priloha_id, "nazev_souboru": soubor[:255],
                }
                stavajici = PodkladovaFaktura.objects.filter(
                    service_item=polozka, period=p, flexi_id=int(f["id"])).first()
                if stavajici is None:
                    stav = "nová"
                elif any(getattr(stavajici, k) != v for k, v in hodnoty.items()):
                    stav = "změna"
                else:
                    stav = "beze změny"
                if zapsat and stav != "beze změny":
                    PodkladovaFaktura.objects.update_or_create(
                        service_item=polozka, period=p, flexi_id=int(f["id"]), defaults=hodnoty)
                radky.append((str(p), polozka.name, f.get("kod"), dodavatel, soubor, stav))
    return radky, nerozpoznane


def stahnout_prilohu(faktura, client=None):
    """Obsah prilohy (bytes, content_type) primo z ABRA."""
    client = client or FlexiClient()
    url = f"{client.url}/c/{client.company}/priloha/{faktura.priloha_id}/content"
    resp = client.session.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type") or "application/pdf"
