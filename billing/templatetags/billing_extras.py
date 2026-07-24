from django import template

register = template.Library()


@register.filter
def kc(value):
    """Formátuje částku stejně jako PDF sestavy (core/client_card_generator.py,
    billing/statement_generator.py): mezera jako oddělovač tisíců, tečka desetin."""
    if value is None:
        return "—"
    return f"{value:,.2f} Kč".replace(",", " ")
