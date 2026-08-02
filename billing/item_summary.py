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

from core.models import BillingLine, CostEntry, ServicePoolItem

from .engine import ABSOLUTE_AMOUNT_TYPES, _consumption_shares, _meter_provides_consumption


def get_item_summary_rows(period, site=None):
    items = (
        ServicePoolItem.objects.select_related("site", "meter")
        .order_by("site__name", "invoice_class", "name")
    )
    if site is not None:
        items = items.filter(site=site)

    rows = []
    for item in items:
        cost_entry = CostEntry.objects.filter(service_item=item, period=period).first()
        if cost_entry is not None:
            naklad = cost_entry.get_amount_czk(period)
            naklad_zdroj = "naklad_za_obdobi" if naklad is not None else "chybi_cenik"
        elif item.default_amount_czk is not None:
            naklad = item.default_amount_czk
            naklad_zdroj = "vychozi_castka"
        else:
            naklad = None
            naklad_zdroj = None

        lines = list(BillingLine.objects.filter(service_item=item, period=period))
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
        if reported_units and not item.meter:
            valid_keys = [
                k for k in item.allocation_keys.select_related("meter", "client_card")
                if k.is_valid_for_period(period) and k.allocation_type not in ABSOLUTE_AMOUNT_TYPES
            ]
            has_meter_keys = any(
                k.meter_id is not None and _meter_provides_consumption(k.meter) for k in valid_keys
            )
            if has_meter_keys:
                _, measured_units = _consumption_shares(item, period, [])
                key_with_meter = next((k for k in valid_keys if k.meter_id), None)
                if key_with_meter:
                    unit_of_measure = key_with_meter.meter.unit_of_measure

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
        })
    return rows
