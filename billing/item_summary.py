"""
Souhrnny prehled Naklad/Vynos PO POLOZKACH zasobniku za obdobi - kolik
polozka skutecne stoji (Naklad za obdobi / Vychozi castka, pripadne
dopocet pres Cenik) vs. kolik se z ni vyfakturuje klientum (soucet
BillingLine), vc. rozdilu (zisk/ztrata). Jeden radek za KAZDOU polozku
(ne za klienta/kartu) - pro interni prehled (core_billingline_prehled,
core/admin.py). NIKDY pro klienty - viz billing/statement_generator.py
pro klientsky vystup.

Vynos se pocita ve DVOU variantach soucasne - "fakturovano" (jen
is_billed=True radky, odpovida tomu, co klient skutecne plati navic) a
"vc. pausalu" (uplne vsechno, i kdyz uz je zahrnute v pausalni platbe
jinde) - Daniel chtel videt obe najednou, ne prepinat.
"""
from decimal import Decimal

from core.models import BillingLine, CostEntry, MeterReading, PriceList, ServicePoolItem

from .engine import ABSOLUTE_AMOUNT_TYPES, _consumption_shares, _meter_provides_consumption


def get_item_summary_rows(period, site=None, with_meters=False):
    """`with_meters=True`: ke kazde merene polozce navic prida
    "meter_breakdown" - seznam radku po JEDNOTLIVYCH meridlech/skupinach
    (viz billing/engine.py _consumption_shares by_meter_out), s jejich
    spotrebou a odhadovanym podilem na Vynosu (podil spotreby * Vynos
    polozky - priblizny rozpad, ne nezavisle dopocitany, viz konverzace
    s Danielem - druha varianta prehledu k porovnani s tou bez rozpadu)."""
    items = (
        ServicePoolItem.objects.select_related("site", "meter")
        .order_by("site__name", "invoice_class", "name")
    )
    if site is not None:
        items = items.filter(site=site)
    items = list(items)

    # Hromadne predem nactene CostEntry/BillingLine/Cenik/odecty pro
    # VSECHNY polozky najednou - stejny vzor jako billing/engine.py
    # calculate_period (readings_cache/price_cache/meter_provides_cache),
    # ktery resil presne tenhle N+1 problem u samotneho vypoctu. Tenhle
    # prehled ale volal CostEntry/BillingLine/_consumption_shares
    # samostatne PRO KAZDOU POLOZKU zvlast - u vetsiho poctu polozek to
    # delalo desitky az stovky dotazu navic a stranka se nacitala i
    # kolem minuty. Viz konverzace s Danielem.
    cost_entries_by_item = {ce.service_item_id: ce for ce in CostEntry.objects.filter(period=period)}
    lines_by_item = {}
    for line in BillingLine.objects.filter(period=period):
        lines_by_item.setdefault(line.service_item_id, []).append(line)
    price_cache = {}
    for pl in (
        PriceList.objects.filter(service_item__in=items)
        .select_related("period")
        .order_by("service_item_id", "-period__year", "-period__month")
    ):
        price_cache.setdefault(pl.service_item_id, []).append(pl)
    meter_provides_cache = {}
    prev_period = period.previous_period()
    relevant_periods = [period] + ([prev_period] if prev_period else [])
    readings_cache = {
        (r.meter_id, r.period_id): r
        for r in MeterReading.objects.filter(period__in=relevant_periods)
    }

    rows = []
    for item in items:
        cost_entry = cost_entries_by_item.get(item.id)
        if cost_entry is not None:
            naklad = cost_entry.get_amount_czk(period, price_cache=price_cache)
            naklad_zdroj = "naklad_za_obdobi" if naklad is not None else "chybi_cenik"
        elif item.default_amount_czk is not None:
            naklad = item.default_amount_czk
            naklad_zdroj = "vychozi_castka"
        else:
            naklad = None
            naklad_zdroj = None

        lines = lines_by_item.get(item.id, [])
        vynos_fakturovano = sum((line.amount for line in lines if line.is_billed), Decimal("0"))
        vynos_vcetne_pausalu = sum((line.amount for line in lines), Decimal("0"))

        if naklad is None and not lines:
            # Polozka se v tomto obdobi vubec nepocitala (napr. sezonni
            # sluzba mimo sezonu) - nema smysl ji v prehledu zobrazovat.
            continue

        # Jednotky - fakturovano dodavatelem vs. co nascitala nase
        # podruzna meridla (stejny princip jako billing/key_detail.py
        # item_losses, tady jen na urovni cele polozky za obdobi).
        reported_units = cost_entry.amount_units if cost_entry else None
        measured_units = None
        unit_of_measure = item.meter.unit_of_measure if item.meter else ""
        meter_breakdown = [] if with_meters else None
        if reported_units and not item.meter:
            valid_keys = [
                k for k in item.allocation_keys.select_related("meter", "client_card")
                if k.is_valid_for_period(period) and k.allocation_type not in ABSOLUTE_AMOUNT_TYPES
            ]
            has_meter_keys = any(
                k.meter_id is not None and _meter_provides_consumption(k.meter, cache=meter_provides_cache)
                for k in valid_keys
            )
            if has_meter_keys:
                by_meter = {} if with_meters else None
                _, measured_units = _consumption_shares(
                    item, period, [], by_meter_out=by_meter,
                    meter_provides_cache=meter_provides_cache, readings_cache=readings_cache,
                )
                key_with_meter = next((k for k in valid_keys if k.meter_id), None)
                if key_with_meter:
                    unit_of_measure = key_with_meter.meter.unit_of_measure
                if by_meter:
                    for info in sorted(by_meter.values(), key=lambda i: -i["contribution"]):
                        meter_breakdown.append({
                            "meter": info["meter"],
                            "consumption": info["consumption"],
                            "contribution": info["contribution"],
                            "cards": info["cards"],
                            "vynos_fakturovano": vynos_fakturovano * info["contribution"],
                            "vynos_vcetne_pausalu": vynos_vcetne_pausalu * info["contribution"],
                        })

        rows.append({
            "site": item.site,
            "invoice_class_key": item.invoice_class,
            "service_item": item,
            "naklad": naklad,
            "naklad_zdroj": naklad_zdroj,
            "vynos_fakturovano": vynos_fakturovano,
            "rozdil_fakturovano": (vynos_fakturovano - naklad) if naklad is not None else None,
            "vynos_vcetne_pausalu": vynos_vcetne_pausalu,
            "rozdil_vcetne_pausalu": (vynos_vcetne_pausalu - naklad) if naklad is not None else None,
            "reported_units": reported_units,
            "measured_units": measured_units,
            "unit_of_measure": unit_of_measure,
            "meter_breakdown": meter_breakdown,
        })
    return rows


def get_naklad_by_class(periods, site=None):
    """Rychla agregace Nakladu (Kc) po Tride pro SEZNAM obdobi najednou -
    pro grafy/prehledy, kde staci soucet, ne rozpad po jednotlivych
    polozkach/mericich (na rozdil od get_item_summary_rows, ktera pro
    KAZDOU polozku dela nekolik dotazu, vc. _consumption_shares u
    merenych polozek). Pri volani jednou na obdobi x vic obdobi najednou
    (napr. graf za poslednich 6 mesicu) to snadno prekroci gunicorn
    WORKER TIMEOUT (30s) - viz konverzace s Danielem, /report/grafy-trid/
    spadlo presne na tohle. Tahle verze dela jen 3 dotazy CELKEM, bez
    ohledu na pocet obdobi/polozek.

    Vraci dict {period.id: {invoice_class_code: Decimal}}.
    """
    items = list(ServicePoolItem.objects.all())
    if site is not None:
        items = [i for i in items if i.site_id == site.id]

    period_ids = [p.id for p in periods]
    cost_entries = {
        (ce.service_item_id, ce.period_id): ce
        for ce in CostEntry.objects.filter(period_id__in=period_ids)
    }

    # Cenikove zaznamy relevantnich polozek nactene JEDNOU - "posledni
    # platny k datu" se pak resolvuje rucne v Pythonu (bez dalsich
    # dotazu), misto volani PriceList.get_price_for_period per (item,
    # period), coz by bylo zase N+1.
    price_lists_by_item = {}
    for pl in (
        PriceList.objects.filter(service_item__in=items)
        .select_related("period")
        .order_by("service_item_id", "-period__year", "-period__month")
    ):
        price_lists_by_item.setdefault(pl.service_item_id, []).append(pl)

    def _price_for(item_id, period):
        for pl in price_lists_by_item.get(item_id, []):
            if (pl.period.year, pl.period.month) <= (period.year, period.month):
                return pl.price_per_unit
        return None

    class_codes = [code for code, _ in ServicePoolItem.InvoiceClass.choices]
    result = {}
    for period in periods:
        totals = {code: Decimal("0") for code in class_codes}
        for item in items:
            cost_entry = cost_entries.get((item.id, period.id))
            if cost_entry is not None:
                if cost_entry.amount_czk is not None:
                    naklad = cost_entry.amount_czk
                elif cost_entry.amount_units is not None:
                    price = _price_for(item.id, period)
                    naklad = cost_entry.amount_units * price if price else None
                else:
                    naklad = None
            elif item.default_amount_czk is not None:
                naklad = item.default_amount_czk
            else:
                naklad = None
            if naklad is not None:
                totals[item.invoice_class] += naklad
        result[period.id] = totals
    return result
