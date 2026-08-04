"""
Podil vah - pro JEDNU vybranou polozku zasobniku a obdobi ukaze vsechny
jeji klice, jejich hodnotu (vahu)/meridlo a skutecny podil na polozce
(share) - interaktivni ekvivalent management commandu diag_polozka_vahy,
ale primo v adminu (core_billingline_podil_vah, core/admin.py).

Pouziva STEJNOU has_meter_keys logiku jako billing/engine.py
calculate_period (viz _meter_provides_consumption) - diag_polozka_vahy
tohle nemela (predchazela rewceniu enginu), takze pro polozky bez
service_item.meter, ale s realnymi podruznymi meridly (napr. "hlavní
odběr elektro NJ") davala jiny vysledek nez skutecny vypocet. Tady je to
vzdy presne konzistentni s tim, co se opravdu vyuctuje.
"""
from decimal import Decimal

from .engine import ABSOLUTE_AMOUNT_TYPES, _consumption_shares, _fixed_amount_for, _meter_provides_consumption, _weighted_shares


def get_weight_share_data(item, period):
    warnings = []
    prev_period = period.previous_period()

    all_keys = list(
        item.allocation_keys.select_related("client_card__client", "client_card__unit", "meter")
    )
    valid_keys = [k for k in all_keys if k.is_valid_for_period(period)]
    invalid_keys = [k for k in all_keys if k not in valid_keys]

    fixed_keys = [k for k in valid_keys if k.allocation_type in ABSOLUTE_AMOUNT_TYPES]
    other_keys = [k for k in valid_keys if k.allocation_type not in ABSOLUTE_AMOUNT_TYPES]

    has_meter_keys = any(
        k.meter_id is not None and _meter_provides_consumption(k.meter) for k in other_keys
    )
    uses_consumption = bool(item.meter) or has_meter_keys

    by_key_share = {}
    by_key_local_share = {}
    total_consumption = None
    if uses_consumption:
        _, total_consumption = _consumption_shares(
            item, period, warnings, by_key_out=by_key_share, by_key_local_out=by_key_local_share
        )
    elif other_keys:
        _weighted_shares(other_keys, period, by_key_out=by_key_share)

    weight_rows = []
    for key in other_keys:
        share = by_key_share.get(key.id)
        meter_state = None
        if key.meter is not None:
            current = key.meter.readings.filter(period=period).first()
            previous = key.meter.readings.filter(period=prev_period).first() if prev_period else None
            meter_state = {
                "previous": previous.value if previous else None,
                "current": current.value if current else None,
                "consumption": key.meter.consumption_for(period),
            }
        weight_rows.append({
            "client": key.client_card.client.name,
            "card": str(key.client_card),
            "type": key.get_allocation_type_display(),
            "meter": key.meter,
            "meter_state": meter_state,
            "value": key.value,
            "weight_unit_label": key.weight_unit_label,
            "share": share,
            "local_share": by_key_local_share.get(key.id),
            "is_billed": key.is_billed,
        })
    weight_rows.sort(key=lambda r: (r["share"] is None, -(r["share"] or Decimal("0"))))

    fixed_rows = []
    for key in fixed_keys:
        amount = _fixed_amount_for(key, item, period, [])
        fixed_rows.append({
            "client": key.client_card.client.name,
            "card": str(key.client_card),
            "type": key.get_allocation_type_display(),
            "value": key.value,
            "amount": amount,
            "deduct_from_pool": key.deduct_from_pool,
            "is_billed": key.is_billed,
        })

    invalid_rows = [
        {
            "client": key.client_card.client.name,
            "card": str(key.client_card),
            "type": key.get_allocation_type_display(),
            "value": key.value,
            "is_active_card": key.client_card.is_active,
            "valid_from": key.valid_from,
            "valid_to": key.valid_to,
        }
        for key in invalid_keys
    ]

    return {
        "uses_consumption": uses_consumption,
        "main_meter": item.meter,
        "total_consumption": total_consumption,
        "weight_rows": weight_rows,
        "fixed_rows": fixed_rows,
        "invalid_rows": invalid_rows,
        "warnings": warnings,
    }
