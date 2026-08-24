"""Kontext pronajimatele - s kterym z nich uzivatel prave pracuje.

Databaze zustava jedna a data obou pronajimatelu v ni lezi vedle sebe
(delit DB jsme zavrhli - klient muze byt najemcem u obou a ciselniky by
se musely udrzovat dvakrat). Uzivatel ale vidi vzdycky prave jednoho:
po prihlaseni si zvoli, s kym pracuje, a admin i sestavy pak ukazuji jen
klienty, plochy, karty, meridla a naklady, ktere pod nej patri.

Sdilene ciselniky (Obdobi, Tridy, Inflace) volba neovlivnuje - ty pod
pronajimatele nepatri.

Neni to bezpecnostni hranice, ale pracovni kontext: admin se kdykoli
prepne v hlavicce bocniho menu. Kdyby mel nekdo videt jen sva data
a nic jineho, patri to na uroven opravneni (accounts.User.sites).

Viz konverzace s Danielem 2026-08-25.
"""
KLIC_SESSION = "pronajimatel_id"


def dostupni():
    """Klienti oznaceni jako Pronajimatel, mezi kterymi se prepina."""
    from core.models import Client

    return Client.objects.filter(is_landlord=True).order_by("name")


# Na jedne strance adminu se pronajimatel potrebuje na peti mistech
# (middleware, hlavicka, rozbalovatko, get_queryset, sestava). Bez tehle
# pameti by to bylo pet stejnych dotazu do databaze na kazdy pozadavek -
# pri latenci Railway znatelne. Drzi se na requestu, takze zije presne
# jeden pozadavek.
_PAMET = "_pronajimatel_cache"


def aktualni(request):
    """Zvoleny pronajimatel, nebo None kdyz jeste zadny zvoleny neni.

    Ulozene id se proveruje proti databazi - klient uz mohl byt smazany
    nebo prestal byt pronajimatelem, a to nesmi skoncit chybou na kazde
    strance."""
    if hasattr(request, _PAMET):
        return getattr(request, _PAMET)
    pk = request.session.get(KLIC_SESSION)
    nalezeny = dostupni().filter(pk=pk).first() if pk else None
    setattr(request, _PAMET, nalezeny)
    return nalezeny


def nastav(request, klient):
    request.session[KLIC_SESSION] = klient.pk
    setattr(request, _PAMET, klient)


def zapomen(request):
    request.session.pop(KLIC_SESSION, None)
    if hasattr(request, _PAMET):
        delattr(request, _PAMET)


def arealy(request):
    """Arealy zvoleneho pronajimatele.

    Bez volby vraci prazdny queryset - radeji neukazat nic nez omylem
    ukazat data druhe osoby."""
    from core.models import Site

    pronajimatel = aktualni(request)
    if pronajimatel is None:
        return Site.objects.none()
    return Site.objects.filter(landlord=pronajimatel)


def id_arealu(request):
    """Same pk arealu - do filtru `__in`, aby se nedotazovala cela tabulka.

    Drzi se stejne jako sam pronajimatel: kazdy filtrovany seznam v adminu
    se na ne pta, a arealu jsou jednotky."""
    pamet = "_arealy_cache"
    if not hasattr(request, pamet):
        setattr(request, pamet, list(arealy(request).values_list("pk", flat=True)))
    return getattr(request, pamet)
