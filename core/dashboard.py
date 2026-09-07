"""Cisla pro dlazdice na uvodni strance adminu.

Uvodni stranka driv ukazovala vestavenou "Spravu webu" - seznam modelu,
ktery uz je cely v levem menu. Misto nej jsou tu dlazdice, ktere
odpovidaji na to, na co se clovek pri prihlaseni pta: kolik mam klientu
a za kolik, jestli uz jdou spocitat odecty a naklady, a co lezi ladem.
Daniel 2026-09-07.

Vsechno je omezene na zvoleneho pronajimatele (core.pronajimatele) -
uvodni stranka nesmi byt jedine misto, kde jsou videt cizi cisla.
Kazda dlazdice ma odkaz na sestavu nebo seznam, kde se to da rozebrat.

Dotazu je zamerne par a jsou to agregace: pri latenci Railway by se
kazdy dotaz navic poznal na dobe nacteni prvni stranky po prihlaseni.
"""
from decimal import Decimal

from django.db.models import Q, Sum
from django.urls import reverse

from core import pronajimatele, volne_plochy
from core.models import (
    CardUnit, ClientCard, CostEntry, InvoiceClassColor, Meter, MeterReading,
    Period, ReadingsClosure, ServicePoolItem, Site, Unit,
)


def prehled(request):
    """Podklad pro templates/admin/index.html - dlazdice a tabulky."""
    obdobi = Period.current()
    arealy = list(pronajimatele.arealy(request))
    if obdobi is None or not arealy:
        return {"obdobi": obdobi, "arealy": arealy}

    zacatek, konec = obdobi.date_range()
    id_arealu = [a.pk for a in arealy]

    karty = (
        ClientCard.objects
        .filter(is_active=True, valid_from__lte=konec,
                card_units__unit__site__in=id_arealu)
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=zacatek))
        .distinct()
    )

    return {
        "obdobi": obdobi,
        "arealy": arealy,
        "klienti": _klienti(karty),
        "najemne": _najemne(karty, obdobi),
        "odecty": _odecty(obdobi, id_arealu),
        "naklady": _naklady(obdobi, id_arealu),
        "volne": _volne_plochy(obdobi, arealy),
    }


def _klienti(karty):
    return {
        "pocet": karty.values("client").distinct().count(),
        "karet": karty.count(),
        "odkaz": reverse("admin:core_clientcard_changelist"),
    }


def _najemne(karty, obdobi):
    """Najem vsech platnych karet za obdobi - uz zkraceny podle poctu
    aktivnich dni, takze karta zacinajici v pulce mesice se necita cela
    (ClientCard.rent_for_period)."""
    celkem = sum(
        (k.rent_for_period(obdobi) or Decimal("0"))
        for k in karty.prefetch_related("card_units__unit")
    )
    return {
        "castka": celkem,
        "odkaz": reverse("admin:core_clientcard_report_najemne"),
    }


def _odecty(obdobi, id_arealu):
    """Kolik meridel uz ma odecet a jestli spravci obdobi uzavreli.

    Virtualni meridla se nepocitaji - ta se nechodi odecitat, dopocitava
    je vzorec (stejne pravidlo jako v sestave Stav odectu)."""
    meridla = Meter.objects.filter(site__in=id_arealu, is_virtual=False)
    celkem = meridla.count()
    hotovo = MeterReading.objects.filter(
        period=obdobi, meter__in=meridla
    ).values("meter").distinct().count()
    return {
        "hotovo": hotovo,
        "celkem": celkem,
        "chybi": celkem - hotovo,
        "uzavreno": ReadingsClosure.objects.filter(
            period=obdobi, site__in=id_arealu
        ).count(),
        "arealu": len(id_arealu),
        "odkaz": reverse("admin:core_meter_report_stav_odectu"),
    }


def _naklady(obdobi, id_arealu):
    """Naklady za obdobi po Tridach + kolik polozek jeste ceka na castku.

    "K doplneni" jsou polozky zasobniku bez vyplnene castky za tohle
    obdobi - at uz zaznam o nakladu vubec nemaji, nebo ho maji prazdny.
    Prazdne pole a nula nejsou totez (viz CostEntry): nula znamena
    "nestalo nic", prazdne "jeste nevim", a prave to brani spocitat
    vyuctovani."""
    polozky = ServicePoolItem.objects.filter(site__in=id_arealu)
    vyplnene = set(
        CostEntry.objects
        .filter(period=obdobi, service_item__in=polozky, amount_czk__isnull=False)
        .values_list("service_item_id", flat=True)
    )
    soucty = (
        CostEntry.objects
        .filter(period=obdobi, service_item__in=polozky)
        .values("service_item__invoice_class")
        .annotate(castka=Sum("amount_czk"))
        .order_by()
    )
    popisky = {
        t.invoice_class: t for t in InvoiceClassColor.objects.all()
    }
    radky = []
    celkem = Decimal("0")
    for s in soucty:
        castka = s["castka"] or Decimal("0")
        if not castka:
            continue
        kod = s["service_item__invoice_class"]
        trida = popisky.get(kod)
        radky.append({
            "kod": kod,
            "nazev": trida.label if trida else kod,
            "css": InvoiceClassColor.css_class_for(kod),
            "castka": castka,
        })
        celkem += castka
    for r in radky:
        r["podil"] = (r["castka"] / celkem * 100) if celkem else 0
    radky.sort(key=lambda r: r["castka"], reverse=True)
    return {
        "radky": radky,
        "celkem": celkem,
        "k_doplneni": polozky.exclude(pk__in=vyplnene).count(),
        "polozek": polozky.count(),
        "odkaz": reverse("admin:core_costentry_changelist"),
    }


def _volne_plochy(obdobi, arealy):
    """Plochy, ktere v obdobi nedrzi zadna aktivni Karta - jejich dil
    nakladu se jinak rozpusti mezi ostatni najemce misto pronajimatele
    (viz core.volne_plochy)."""
    plochy = list(volne_plochy.bez_karty(obdobi, sites=arealy))
    return {
        "pocet": len(plochy),
        "m2": sum((u.area_m2 or Decimal("0")) for u in plochy),
        "prvni": plochy[:6],
        "odkaz": reverse("admin:core_unit_report_bez_karty"),
    }
