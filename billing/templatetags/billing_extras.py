from django import template

from billing.statement_generator import format_price_per_unit, format_units

register = template.Library()


@register.filter
def kc(value):
    """Formátuje částku stejně jako PDF sestavy (core/client_card_generator.py,
    billing/statement_generator.py): mezera jako oddělovač tisíců, tečka desetin."""
    if value is None:
        return "—"
    return f"{value:,.2f} Kč".replace(",", " ")


@register.filter
def percent(value, decimals=3):
    """Formátuje podíl (0-1) jako procenta, např. 0.061317 -> '6.132 %'."""
    if value is None:
        return "—"
    return f"{value * 100:.{decimals}f} %"


@register.filter
def units_display(line):
    return format_units(line["units"], line["unit_of_measure"])


@register.filter
def price_per_unit_display(line):
    return format_price_per_unit(line["price_per_unit"], line["unit_of_measure"])
