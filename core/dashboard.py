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
import json
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

from core import pronajimatele, volne_plochy
from core.models import (
    BillingLine, Client, ClientCard, CostEntry, InvoiceClassColor, Meter,
    MeterReading, Period, PriceList, ReadingsClosure, ServicePoolItem,
)

# Kolik dopredu se hlida konec Karty. Tri mesice je doba, za kterou se
# jeste da najit nahradnik nebo domluvit prodlouzeni - kratsi varovani
# uz je jen konstatovani. Daniel 2026-09-07.
KONEC_KARTY_DNI = 90


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
        "vyuctovani": _vyuctovani(obdobi, karty, id_arealu),
        "koncici": _koncici_karty(id_arealu),
        "insolvence": _insolvence(request),
        "dph": _dph(request, obdobi, arealy),
        "graf": _graf_nakladu(obdobi, id_arealu),
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

    "K doplneni" jsou polozky zasobniku, u kterych billing/engine.py
    polozku pri prepoctu preskoci - bez CostEntry, ktery se da prevest
    na Kc (CostEntry.get_amount_czk - primo, nebo mnozstvi x cena z
    Ceniku/klice), A bez Vychozi mesicni castky.

    Puvodni verze kontrolovala jen CostEntry.amount_czk, coz falesne
    hlasilo jako chybejici polozky se zadanim "Jen mnozstvi" (vodne/
    stocne, pelety) - tam se Kc zamerne NEVYPLNUJE, dopocita se z
    Ceniku. Dalsi verze pridala "nebo ma vyplnene mnozstvi", coz zase
    falesne hlasilo jako HOTOVE polozky typu "Mnozstvi i castka"
    (elektrina, teplo) se zadanym mnozstvim, ale BEZ ceny (faktura jeste
    nedosla) - tam zadna Kc castka nejde dopocitat vubec (viz elektrina
    FM, konverzace s Danielem 2026-09-08).

    Cena z Ceniku oznacena jako "Predbezna cena" (odhad) se tu NEPOCITA
    za hotovy udaj, i kdyz billing/engine.py (CostEntry.get_amount_czk)
    ji na skutecny vypocet klidne pouzije - "s odhadem nemuzeme
    pracovat" (Daniel 2026-09-08): tenhle prehled ma ukazovat, co je
    OPRAVDU podlozene, ne provizorium do prichodu faktury. Proto se
    nepouziva rovnou CostEntry.get_amount_czk, ale _amount_bez_odhadu
    nize."""
    polozky = list(ServicePoolItem.objects.filter(site__in=id_arealu))

    entries_by_item = {}
    for ce in CostEntry.objects.filter(period=obdobi, service_item__in=polozky):
        entries_by_item.setdefault(ce.service_item_id, []).append(ce)

    # Hromadne nacteny Cenik pro vsechny polozky najednou (stejny vzor
    # jako price_cache v billing/engine.py calculate_period) - misto
    # dotazu na Cenik zvlast pro kazdou polozku v cyklu nize.
    price_cache = {}
    for pl in (
        PriceList.objects.filter(service_item__in=polozky)
        .order_by("service_item_id", "-period__year", "-period__month")
    ):
        price_cache.setdefault(pl.service_item_id, []).append(pl)

    def _amount_bez_odhadu(ce):
        """Jako CostEntry.get_amount_czk, ale cenu z Ceniku pouzije jen
        kdyz NENI oznacena jako Predbezna cena."""
        if ce.amount_czk is not None:
            return ce.amount_czk
        if ce.amount_units is None:
            return None
        if ce.price_per_unit is not None:
            return (ce.amount_units * ce.price_per_unit).quantize(Decimal("0.01"))
        radek = PriceList.radek_pro_obdobi(ce.service_item, obdobi, price_cache=price_cache)
        if radek is None or radek.is_estimate:
            return None
        return (ce.amount_units * radek.price_per_unit).quantize(Decimal("0.01"))

    popisky = {t.invoice_class: t for t in InvoiceClassColor.objects.all()}
    castka_by_trida = {}
    celkem = Decimal("0")
    hotovo = set()
    for item in polozky:
        # Stejna prednost jako v enginu: kdyz ma polozka za obdobi
        # CostEntry (i kdyby se nepodarilo dopocitat Kc), Vychozi castka
        # se nepouzije - jen kdyz CostEntry chybi uplne.
        item_entries = entries_by_item.get(item.id, [])
        castka = None
        if item_entries:
            for ce in item_entries:
                resolved = _amount_bez_odhadu(ce)
                if resolved is not None:
                    castka = (castka or Decimal("0")) + resolved
            if castka is not None:
                hotovo.add(item.id)
        elif item.default_amount_czk is not None:
            castka = item.default_amount_czk
            hotovo.add(item.id)
        if castka:
            castka_by_trida[item.invoice_class] = castka_by_trida.get(item.invoice_class, Decimal("0")) + castka
            celkem += castka

    radky = []
    for kod, castka in castka_by_trida.items():
        trida = popisky.get(kod)
        radky.append({
            "kod": kod,
            "nazev": trida.label if trida else kod,
            "css": InvoiceClassColor.css_class_for(kod),
            "castka": castka,
            "podil": (castka / celkem * 100) if celkem else 0,
        })
    radky.sort(key=lambda r: r["castka"], reverse=True)

    return {
        "radky": radky,
        "celkem": celkem,
        "k_doplneni": len(polozky) - len(hotovo),
        "polozek": len(polozky),
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


def _vyuctovani(obdobi, karty, id_arealu):
    """Kolik Karet uz ma za obdobi spocitane radky vyuctovani.

    Rika, jak daleko je uzaverka: dokud cislo nesedi s poctem platnych
    karet, vyuctovani se jeste nepocitalo (nebo neproslo cele)."""
    spocitano = (
        BillingLine.objects
        .filter(period=obdobi, service_item__site__in=id_arealu)
        .values("client_card").distinct().count()
    )
    celkem = karty.count()
    return {
        "spocitano": spocitano,
        "celkem": celkem,
        "hotovo": celkem and spocitano >= celkem,
        "odkaz": reverse("admin:core_billingline_prehled"),
    }


def _koncici_karty(id_arealu):
    """Karty, kterym do KONEC_KARTY_DNI dnu skonci platnost.

    Zamerne Karty, ne Smlouvy: rozuctovani i najem visi na Karte a jsou
    karty bez smlouvy - konec smlouvy by tedy cast pripadu minul."""
    dnes = timezone.localdate()
    karty = list(
        ClientCard.objects
        .filter(is_active=True, valid_to__isnull=False,
                valid_to__gte=dnes, valid_to__lte=dnes + timedelta(days=KONEC_KARTY_DNI),
                card_units__unit__site__in=id_arealu)
        .select_related("client")
        .order_by("valid_to")
        .distinct()[:6]
    )
    return {
        "pocet": len(karty),
        "karty": karty,
        "dni": KONEC_KARTY_DNI,
        "odkaz": reverse("admin:core_clientcard_changelist"),
    }


def _insolvence(request):
    """Klienti s bezicim insolvencnim rizenim.

    Cte se jen ULOZENY vysledek mesicni kontroly proti ARES
    (Client.insolvency_status) - na uvodni strance se do rejstriku
    nechodi, to je dotaz po siti a stranka by na nej cekala."""
    klienti = pronajimatele.klienti(request).filter(
        is_active=True, insolvency_status=Client.InsolvencyStatus.ACTIVE
    )
    return {
        "pocet": klienti.count(),
        "klienti": list(klienti[:5]),
        "odkaz": reverse("admin:core_client_kontrola_rizik"),
    }


def _dph(request, obdobi, arealy):
    """Koeficient DPH za rok k vybranemu obdobi - stejny vypocet, jaky
    ukazuje sestava Prehled najemneho (ClientCardAdmin), aby dlazdice
    a sestava nerekly kazda neco jineho.

    Pocita se jen u pronajimatele, ktery je platcem DPH - u neplatce
    (Daniel jako fyzicka osoba u DV) koeficient nedava smysl.
    """
    from django.contrib.admin.sites import site as admin_site

    from core.admin import ClientCardAdmin

    pronajimatel = pronajimatele.aktualni(request)
    if pronajimatel is None or not pronajimatel.vat_payer:
        return None
    site_ids = [a.pk for a in arealy]
    koef = ClientCardAdmin(ClientCard, admin_site)._koeficient_dph_za_rok(
        obdobi, site_ids
    )
    if not koef:
        return None
    koef["odkaz"] = reverse("admin:core_clientcard_report_najemne")
    return koef


def _graf_nakladu(obdobi, id_arealu):
    """Naklady po mesicich a Tridach - data pro sloupcovy graf Unfoldu.

    Jen mesice od ledna do vybraneho obdobi: obdobi se zakladaji dopredu
    tlacitkem "Generovat pro cely rok", takze prazdne sloupce budoucich
    mesicu by graf jen natahly. Stejna uvaha jako u koeficientu DPH.
    """
    mesice = list(
        Period.objects.filter(year=obdobi.year, month__lte=obdobi.month)
        .order_by("month")
    )
    if not mesice:
        return None
    poradi = {p.pk: i for i, p in enumerate(mesice)}

    tridy = {t.invoice_class: t for t in InvoiceClassColor.objects.all()}
    data = {}
    for radek in (CostEntry.objects
                  .filter(period__in=mesice, service_item__site__in=id_arealu)
                  .values("period_id", "service_item__invoice_class")
                  .annotate(castka=Sum("amount_czk"))
                  .order_by()):
        kod = radek["service_item__invoice_class"]
        data.setdefault(kod, [0] * len(mesice))
        data[kod][poradi[radek["period_id"]]] = float(radek["castka"] or 0)

    if not any(any(hodnoty) for hodnoty in data.values()):
        return None

    datasets = []
    for kod, hodnoty in sorted(data.items(), key=lambda p: -sum(p[1])):
        trida = tridy.get(kod)
        datasets.append({
            "label": trida.label if trida else kod,
            "data": hodnoty,
            "backgroundColor": trida.text_color_light if trida else "#888888",
            "borderRadius": 3,
        })
    return {
        "data": json.dumps({
            "labels": ["%02d" % p.month for p in mesice],
            "datasets": datasets,
        }),
        "options": json.dumps({
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {"legend": {"position": "bottom"}},
            "scales": {"x": {"stacked": True}, "y": {"stacked": True}},
        }),
        "rok": obdobi.year,
        "odkaz": reverse("admin:core_costentry_changelist"),
    }
