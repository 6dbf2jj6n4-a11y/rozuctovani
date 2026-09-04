"""
Kontrola rizika u klientu podle ARES - spolecna logika pro management
prikaz (mesicni kontrola, viz core/management/commands/zkontrolovat_rizika.py)
i pro tlacitko "Zkontrolovat rizika (ARES)" nad seznamem Klientu
(core.admin.ClientAdmin.kontrola_rizik_view).

Drzi se to tady, aby obe cesty delaly opravdu totez - kdyby si admin
volal prikaz pres call_command a jen chytal text, nemel by z ceho
poskladat odkazy na konkretni klienty.
"""
import time

from core.ares_client import PRAVNI_FORMA_OSVC, lookup_company, lookup_trade_register
from core.models import Client

# Slusne tempo dotazu na verejne ARES API - mezi jednotlivymi dotazy se
# ceka, at se na nas nezlobi.
PAUZA = 0.2


def zkontrolovat(dry_run=False, pauza=PAUZA):
    """Projde aktivni klienty s ICO a vrati nalezena rizika.

    Vraci dict se seznamy (viz klice nize). Pokud dry_run neni zapnuty,
    rovnou uklada zmeneny nazev (likvidace) a insolvency_status - tim se
    klient v seznamu obarvi cervene (ClientAdmin.name_display).
    """
    clients = Client.objects.filter(is_active=True).exclude(ico="").order_by("name")

    nove_likvidace = []      # (client, puvodni_nazev, nazev_z_ares)
    drive_likvidace = []     # client
    nove_insolvence = []     # client
    vyresene_insolvence = []  # client
    bez_provozovny = []      # (client, pocet_zaniklych)
    nenalezeno = []          # client

    for client in clients:
        company = lookup_company(client.ico)
        if not company or not company.get("name"):
            nenalezeno.append(client)
            time.sleep(pauza)
            continue

        # 1) likvidace v nazvu
        ares_name = company["name"]
        if "v likvidaci" in ares_name.lower():
            if "v likvidaci" in client.name.lower():
                drive_likvidace.append(client)
            else:
                nove_likvidace.append((client, client.name, ares_name))
                if not dry_run:
                    client.name = ares_name
                    client.save(update_fields=["name"])

        # 2) insolvencni rejstrik
        raw_stav = company.get("insolvence_stav")
        new_status = raw_stav.lower() if raw_stav in ("AKTIVNI", "HISTORICKY") else ""
        if new_status != client.insolvency_status:
            if new_status == "aktivni":
                nove_insolvence.append(client)
            elif client.insolvency_status == "aktivni":
                vyresene_insolvence.append(client)
            if not dry_run:
                client.insolvency_status = new_status
                client.save(update_fields=["insolvency_status"])

        # 3) OSVC - informativni pohled do zivnostenskeho rejstriku
        if company.get("pravni_forma") == PRAVNI_FORMA_OSVC:
            trade = lookup_trade_register(client.ico)
            if trade and trade.get("provozovny_aktivni") == 0:
                bez_provozovny.append((client, trade["provozovny_zanikle"]))
            time.sleep(pauza)

        time.sleep(pauza)

    return {
        "dry_run": dry_run,
        "zkontrolovano": clients.count(),
        "nove_likvidace": nove_likvidace,
        "drive_likvidace": drive_likvidace,
        "nove_insolvence": nove_insolvence,
        "vyresene_insolvence": vyresene_insolvence,
        "bez_provozovny": bez_provozovny,
        "nenalezeno": nenalezeno,
    }


def je_neco_k_reseni(vysledek):
    """Nasla kontrola neco, co chce reakci? (nove riziko, ne jen stav)"""
    return bool(vysledek["nove_likvidace"] or vysledek["nove_insolvence"])
