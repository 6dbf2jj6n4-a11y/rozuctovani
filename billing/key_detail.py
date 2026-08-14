"""
Auditovaci detail vyuctovani PO JEDNOTLIVYCH KLICICH (AllocationKey) pro
jednoho klienta a obdobi - pouziva se jen pro cteni v adminu
(core_billingline_detail_client, viz core/admin.py), NIKDY pro skutecny
vypocet vyuctovani (ten zustava beze zmeny v billing/engine.py).

BillingLine uklada jen SOUCET pres vsechny klice klienta pro danou
polozku zasobniku (typicky je klic jen jeden, ale schema pripousti
vic - napr. podruzne meridlo + zbytkovy vazeny podil soucasne). Tady
se pro kazdy klic klienta dopocita jeho VLASTNI podil/jednotky/castka
zvlast, opetovnym pouzitim stejnych (needitovanych) vypocetnich funkci
z engine.py (_consumption_shares/_weighted_shares s by_key_out), takze
vysledek je vzdy konzistentni se skutecnym vypoctem.
"""
from decimal import Decimal

from core.models import AllocationKey, BillingLine, CostEntry, PriceList
from .engine import (
    ABSOLUTE_AMOUNT_TYPES,
    _consumption_shares,
    _fixed_amount_for,
    _meter_provides_consumption,
    _weighted_shares,
)


def get_key_rows_for_client(client, period):
    """Vrati (rows, warnings, item_losses).

    `rows`: seznam radku (dict) - jeden za kazdy platny Klic klienta v danem
    obdobi, napric vsemi Kartami klienta a polozkami zasobniku, na ktere ma
    v tomto obdobi vyuctovanou polozku (BillingLine).

    `item_losses`: INTERNI vodítko (nikdy nezobrazovat klientovi - viz
    konverzace s Danielem, klientum se ztraty schovaji do ceny/jednotku,
    ne zobrazuji zvlast) - u polozek BEZ hlavniho meridla (implicitni
    "celek" dopocitany jako soucet podruznych meridel, viz
    billing/engine.py _consumption_shares) porovna fakturovane mnozstvi
    od dodavatele (CostEntry.amount_units) s tim, co skutecne nascitaly
    nase podruzna meridla - rozdil je nezachycena spotreba (spolecne
    prostory bez klice, technicke ztraty, chybejici odecet...). Jeden
    zaznam za KAZDOU polozku (ne za kazdy klic/kartu)."""
    warnings = []
    rows = []
    item_losses = []
    seen_loss_items = set()

    lines = (
        BillingLine.objects.filter(period=period, client_card__client=client)
        .select_related("client_card", "service_item", "service_item__meter", "service_item__site")
        .order_by("service_item__name")
    )

    seen_items = set()
    prev_period = period.previous_period()

    for line in lines:
        si = line.service_item
        if (line.client_card_id, si.id) in seen_items:
            continue
        seen_items.add((line.client_card_id, si.id))

        calc = line.calc_detail or {}
        total_cost = Decimal(calc["total_cost"]) if calc.get("total_cost") is not None else None
        remaining_cost = Decimal(calc["remaining_cost"]) if calc.get("remaining_cost") is not None else None

        all_keys = list(
            si.allocation_keys.select_related("client_card", "client_card__unit", "meter")
        )
        valid_keys = [k for k in all_keys if k.is_valid_for_period(period)]
        client_keys = [k for k in valid_keys if k.client_card_id == line.client_card_id]

        # Podily po jednotlivych klicich (vsech klientu polozky - normalizace
        # potrebuje znat vsechny) - stejne funkce jako skutecny vypocet.
        by_key_share = {}
        by_key_local_share = {}
        total_consumption = None
        has_meter_keys = any(
            k.meter_id is not None and _meter_provides_consumption(k.meter)
            for k in valid_keys if k.allocation_type not in ABSOLUTE_AMOUNT_TYPES
        )
        if si.meter or has_meter_keys:
            _, total_consumption = _consumption_shares(
                si, period, warnings, by_key_out=by_key_share, by_key_local_out=by_key_local_share
            )
        else:
            weight_keys = [k for k in valid_keys if k.allocation_type not in ABSOLUTE_AMOUNT_TYPES]
            _weighted_shares(weight_keys, period, by_key_out=by_key_share)

        if (
            not si.meter and has_meter_keys and total_consumption is not None
            and si.id not in seen_loss_items
        ):
            seen_loss_items.add(si.id)
            cost_entry = CostEntry.objects.filter(service_item=si, period=period).first()
            reported_units = cost_entry.amount_units if cost_entry else None
            if reported_units:
                loss_units = reported_units - total_consumption
                key_with_meter = next((k for k in valid_keys if k.meter_id), None)
                item_losses.append({
                    "service_item": si.name,
                    "invoice_class_key": si.invoice_class,
                    "reported_units": reported_units,
                    "measured_units": total_consumption,
                    "loss_units": loss_units,
                    "loss_pct": (loss_units / reported_units) if reported_units else None,
                    "unit_of_measure": key_with_meter.meter.unit_of_measure if key_with_meter else "",
                })

        # Meridla, ktera jsou na teto polozce SAMA O SOBE take samostatne
        # uctovana (maji vlastni klic) - jen tahle se skutecne odecitaji od
        # sveho nadrazeneho meridla v billing/engine.py _owned_consumption,
        # takze jen tahle se maji zobrazit jako "odectene deti" pod master
        # radkem (viz nize).
        billed_meter_ids = {
            k.meter_id for k in valid_keys
            if k.meter_id is not None and k.allocation_type not in ABSOLUTE_AMOUNT_TYPES
        }

        for key in client_keys:
            row = {
                "site": si.site.name,
                "service_item": si.name,
                "invoice_class_key": si.invoice_class,
                "invoice_class": si.get_invoice_class_display(),
                "key_label": key.get_allocation_type_display(),
                "meter_code": None,
                "previous_state": None,
                "current_state": None,
                "consumption": None,
                "share": None,
                "local_share": None,
                "units": None,
                "unit_of_measure": None,
                "price_per_unit": None,
                "amount": Decimal("0"),
                "sub_meters": [],
                "is_billed": key.is_billed,
            }

            if key.allocation_type in ABSOLUTE_AMOUNT_TYPES:
                amount = _fixed_amount_for(key, si, period, warnings)
                row["amount"] = amount if amount is not None else Decimal("0")
                if key.allocation_type == AllocationKey.AllocationType.AREA_PRICE:
                    # Cena z klíče (sjednaná cena karty) má přednost před Ceníkem
                    # - viz billing/engine.py _fixed_amount_for.
                    price = key.unit_price if key.unit_price is not None else PriceList.get_price_for_period(si, period)
                    row["units"] = key.value
                    row["unit_of_measure"] = "m²"
                    row["price_per_unit"] = price
            else:
                share = by_key_share.get(key.id)
                row["share"] = share
                row["local_share"] = by_key_local_share.get(key.id)

                # Prioritne meridlo primo u klice (i kdyz jeho typ neni
                # "Podruzne meridlo" - napr. "Podle vahy" s rucne zadanou
                # vahou muze mit meridlo dopojene jen informativne, pro
                # kontrolu, ze zadana vaha zhruba odpovida skutecne
                # spotrebe - viz konverzace o klici E_N2). Na samotny
                # vypocet (ktery cte jen key.meter u typu SUBMETER) to
                # nema vliv, jde jen o zobrazeni.
                meter_for_state = key.meter or si.meter

                if meter_for_state is not None:
                    row["meter_code"] = meter_for_state.code or meter_for_state.name
                    current_reading = meter_for_state.readings.filter(period=period).first()
                    previous_reading = (
                        meter_for_state.readings.filter(period=prev_period).first() if prev_period else None
                    )
                    row["previous_state"] = previous_reading.value if previous_reading else None
                    row["current_state"] = current_reading.value if current_reading else None
                    row["consumption"] = meter_for_state.consumption_for(period)
                    row["unit_of_measure"] = meter_for_state.unit_of_measure

                    if meter_for_state.is_virtual:
                        for leaf, leaf_sign in meter_for_state.consumption_leaves():
                            leaf_current = leaf.readings.filter(period=period).first()
                            leaf_previous = (
                                leaf.readings.filter(period=prev_period).first() if prev_period else None
                            )
                            row["sub_meters"].append({
                                "meter_code": leaf.code or leaf.name,
                                "sign": leaf_sign,
                                "previous_state": leaf_previous.value if leaf_previous else None,
                                "current_state": leaf_current.value if leaf_current else None,
                                "consumption": leaf.consumption_for(period),
                                "unit_of_measure": leaf.unit_of_measure,
                            })
                            # Fyzicka podruzna meridla listu (napr. E_A7 ->
                            # E_A1..E_A6) uz nejsou soucasti hodnoty, kterou
                            # list prispiva do vzorce - do nej vstupuje jen
                            # jeho vlastni zbytek (_consumption_net_of_children,
                            # viz core/models.py _formula_consumption_for).
                            # Zobrazit je pod listem s opacnym znamenkem, aby
                            # soucet radku sedel s celkovou spotrebou
                            # virtualniho meridla (jinak by +E_A7 vypadalo jako
                            # surovych 1214 misto vlastnich 473). Odecitaji se
                            # VSECHNY prime deti - shodne s netting ve vzorci.
                            # Viz konverzace s Danielem 2026-08-13.
                            for leaf_child in leaf.children.all():
                                lc_current = leaf_child.readings.filter(period=period).first()
                                lc_previous = (
                                    leaf_child.readings.filter(period=prev_period).first()
                                    if prev_period else None
                                )
                                row["sub_meters"].append({
                                    "meter_code": leaf_child.code or leaf_child.name,
                                    "sign": -leaf_sign,
                                    "previous_state": lc_previous.value if lc_previous else None,
                                    "current_state": lc_current.value if lc_current else None,
                                    "consumption": leaf_child.consumption_for(period),
                                    "unit_of_measure": leaf_child.unit_of_measure,
                                })

                    # Realna hierarchie (Meter.parent_meter) - podrizena
                    # meridla, ktera jsou sama o sobe samostatne uctovana
                    # (billed_meter_ids), se od surove spotreby tohoto
                    # meridla odectou (viz billing/engine.py
                    # _owned_consumption) - zobrazit je pod master radkem
                    # se znamenkem minus, aby bylo videt, kam se presunuly.
                    for child in meter_for_state.children.all():
                        if child.id not in billed_meter_ids:
                            continue
                        child_current = child.readings.filter(period=period).first()
                        child_previous = (
                            child.readings.filter(period=prev_period).first() if prev_period else None
                        )
                        row["sub_meters"].append({
                            "meter_code": child.code or child.name,
                            "sign": -1,
                            "previous_state": child_previous.value if child_previous else None,
                            "current_state": child_current.value if child_current else None,
                            "consumption": child.consumption_for(period),
                            "unit_of_measure": child.unit_of_measure,
                        })

                if share is not None and remaining_cost is not None:
                    row["amount"] = (remaining_cost * share).quantize(Decimal("0.01"))

                if share is not None and total_consumption:
                    row["units"] = (share * total_consumption).quantize(Decimal("0.001"))
                    if meter_for_state is not None:
                        row["unit_of_measure"] = meter_for_state.unit_of_measure
                    elif si.meter:
                        row["unit_of_measure"] = si.meter.unit_of_measure
                    if total_cost:
                        row["price_per_unit"] = (total_cost / total_consumption).quantize(Decimal("0.0001"))

            rows.append(row)

    return rows, warnings, item_losses
