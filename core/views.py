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


def vyber_pronajimatele(request):
    """Stranka s volbou pronajimatele, se kterym uzivatel pracuje.

    Sem posila config.middleware.PronajimatelMiddleware kazdeho, kdo do
    adminu prijde bez zvoleneho pronajimatele. Viz core/pronajimatele.py.
    """
    from django.contrib.admin import site as admin_site
    from django.shortcuts import redirect, render

    from core import pronajimatele

    dostupni = list(pronajimatele.dostupni())
    kam = request.GET.get("dal") or "/admin/"
    # Odkud jsme prisli si drzime v adresa, ne v session - uzivatel muze
    # mit otevrenych vic zalozek a kazda miri jinam.
    if request.method == "POST":
        zvoleny = next(
            (p for p in dostupni if str(p.pk) == request.POST.get("pronajimatel")), None
        )
        if zvoleny is not None:
            pronajimatele.nastav(request, zvoleny)
            return redirect(request.POST.get("dal") or "/admin/")

    return render(request, "admin/vyber_pronajimatele.html", {
        **admin_site.each_context(request),
        "title": "Se kterým pronajímatelem chcete pracovat?",
        "dostupni": dostupni,
        "aktualni": pronajimatele.aktualni(request),
        "dal": kam,
    })


def prepnout_pronajimatele(request, pk):
    """Prepnuti z hlavicky menu - vrati uzivatele tam, odkud prisel."""
    from django.shortcuts import redirect

    from core import pronajimatele

    zvoleny = pronajimatele.dostupni().filter(pk=pk).first()
    if zvoleny is not None:
        pronajimatele.nastav(request, zvoleny)
    # Zpatky na tutez stranku: po prepnuti se ma jen prekreslit obsah.
    # Referer muze chybet (primo zadana adresa), pak jde uzivatel na uvod.
    return redirect(request.META.get("HTTP_REFERER") or "/admin/")
