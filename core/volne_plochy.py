"""Plochy, které v daném období nedrží žádná aktivní Karta.

Když nájemci skončí smlouva a plochu nikdo nepřevezme, nepřestane stát
peníze - jen se její díl nákladů rozpustí mezi ostatní nájemce. To je
špatně: prázdnou plochu má nést pronajímatel. Daniel 2026-09-05: "pokud
Aktiv Novostav skončí a nemáme náhradu, musí prostory přejít na
pronajímatele."

Samo se to dít nemá - systém neví, jestli náhradní nájemce nedorazí za
týden. Proto se jen nahlásí (při přepočtu Období i v samostatné sestavě)
a převod potvrzuje člověk.
"""
from datetime import date

from core.models import CardUnit, ClientCard, Unit

DALEKO = date(9999, 12, 31)


def bez_karty(period, site=None, sites=None):
    """Plochy, které v období `period` nedrží žádná aktivní Karta.

    Rozhoduje PŘEKRYV platnosti karty s obdobím, ne pouhý příznak
    Aktivní - karta, která skončila loni, plochu nedrží, i když u ní
    příznak zůstal viset."""
    zacatek, konec = period.date_range()
    units = Unit.objects.select_related("site")
    if site is not None:
        units = units.filter(site=site)
    elif sites is not None:
        units = units.filter(site__in=sites)

    drzene = set()
    for cu in (CardUnit.objects
               .filter(card__is_active=True, unit__in=units)
               .select_related("card")):
        karta = cu.card
        if karta.valid_from <= konec and (karta.valid_to or DALEKO) >= zacatek:
            drzene.add(cu.unit_id)
    return units.exclude(id__in=drzene).order_by("site__name", "name")


def karta_pronajimatele(site, period):
    """Karta pronajímatele areálu platná v období, nebo None.

    Pronajímatel je vlastnost Areálu (Site.landlord). Když má v areálu
    víc platných karet najednou, vrátí se ta, která začala později -
    typicky ta nová po obměně."""
    if site.landlord_id is None:
        return None
    zacatek, konec = period.date_range()
    karty = [
        k for k in ClientCard.objects.filter(client_id=site.landlord_id, is_active=True)
        if k.valid_from <= konec and (k.valid_to or DALEKO) >= zacatek
        and k.card_units.filter(unit__site=site).exists()
    ]
    if not karty:
        return None
    return sorted(karty, key=lambda k: k.valid_from)[-1]


def prevest(units, karta):
    """Přidá plochy na kartu pronajímatele. Vrací počet skutečně přidaných."""
    pridano = 0
    for unit in units:
        _, vznikl = CardUnit.objects.get_or_create(card=karta, unit=unit)
        pridano += 1 if vznikl else 0
    return pridano


def hlaseni(period, sites):
    """Text do varování při přepočtu, nebo None když je vše obsazené."""
    volne = list(bez_karty(period, sites=sites))
    if not volne:
        return None
    podle_arealu = {}
    for u in volne:
        podle_arealu.setdefault(u.site.name, []).append(u.name)
    popis = "; ".join(
        "{}: {}".format(areal, ", ".join(nazvy))
        for areal, nazvy in sorted(podle_arealu.items())
    )
    return (
        "{} plocha(y) nedrží v {} žádná Karta - jejich díl nákladů nesou "
        "ostatní nájemci. Pokud za ně není náhrada, převeď je na kartu "
        "pronajímatele (Reporty → Plochy bez karty): {}"
    ).format(len(volne), period, popis)
