"""Jak se ve vyuctovani ukaze rozdil mezi fakturovanym a namerenym
mnozstvim (ztraty v rozvodech, spolecne prostory, rozdil mereni).

Castka klienta je v obou zpusobech STEJNA - meni se jen, ktere dve cisla
se mu ukazou jako "jednotky x cena":

  do ceny (vychozi):  namerene jednotky x (naklad / namerene mnozstvi)
  do jednotek:        (namerene + podil na rozdilu) x cena z faktury

Matematicky: namerene x (fakturovane / namerene) x (naklad / fakturovane)
= namerene x (naklad / namerene). Podil na rozdilu (surcharge_units) a cenu
z faktury (base_price_per_unit) uz pri vypoctu uklada billing/engine.py
surcharge_split, tady se nic nepocita znovu.

Prepina se po Tridach - InvoiceClassColor.ztraty_do_jednotek. Daniel
2026-10-14: "doposud jsem ztraty dal do jednotek spotreby a cenu nechal
stejnou", chce mit volbu, vychozi zustava do ceny.
"""


def jednotky_a_cena(units, price_per_unit, base_price_per_unit, surcharge_units, do_jednotek):
    """Vrati (jednotky, cena za jednotku) k zobrazeni.

    Do jednotek jen u radku, ktery ma rozpad na vlastni spotrebu a rozdil
    (surcharge_split) - pausaly, plocha x cena a starsi obdobi bez rozpadu
    se ukazuji beze zmeny."""
    if (do_jednotek and units is not None and base_price_per_unit is not None
            and surcharge_units is not None):
        return units + surcharge_units, base_price_per_unit
    return units, price_per_unit
