"""Verejne (neadminovske) view funkce core aplikace."""
from django.http import HttpResponse


def class_colors_css(request):
    """Dynamicky CSS s barvami textu podle Tridy - generuje se z
    InvoiceClassColor (Nastavení -> Barvy tříd), aby si Daniel mohl barvy
    prebarvit v adminu bez zasahu do kodu.

    Proc CSS a ne inline style na kazdem radku: jeden odstin necte dobre
    ve svetlem i tmavem motivu, takze je potreba varianta pro kazdy - a
    inline style se na motiv navazat neumi. Unfold pridava tridu "dark"
    na <html> (i v rezimu "auto" podle prefers-color-scheme, viz
    unfold/layouts/skeleton.html), takze staci navesit se na ni.

    Zapojeno pres UNFOLD["STYLES"] v config/settings.py, takze plati na
    vsech admin strankach. Viz konverzace s Danielem 2026-08-16.
    """
    from core.models import InvoiceClassColor

    lines = [
        "/* generovano core.views.class_colors_css z Nastavení -> Barvy tříd */"
    ]
    for color in InvoiceClassColor.objects.all():
        css_class = InvoiceClassColor.css_class_for(color.invoice_class)
        lines.append(f".{css_class} {{ color: {color.text_color_light}; }}")
        lines.append(f"html.dark .{css_class} {{ color: {color.text_color_dark}; }}")

    response = HttpResponse("\n".join(lines), content_type="text/css")
    # Bez cache, aby se zmena barvy v adminu projevila hned po reloadu -
    # je to par radku CSS a jeden trivialni dotaz.
    response["Cache-Control"] = "no-cache"
    return response
