"""Dynamicke doplnky pro Unfold branding (config.settings.UNFOLD) - v samostatnem
modulu, aby settings.py mohl na SITE_SUBHEADER odkazovat jako na retezec
("core.admin_branding.site_subheader"), ktery Unfold importuje az za behu
pozadavku (ne pri startu Django), takze neni problem s poradim inicializace
aplikaci."""


def site_subheader(request):
    """Pronajimatel, se kterym uzivatel prave pracuje.

    Drive to byl prvni klient s priznakem "Pronajimatel" - od zavedeni
    volby (core/pronajimatele.py) ukazuje toho zvoleneho, aby bylo na
    kazde strance videt, ci data mam pred sebou."""
    from core import pronajimatele

    pronajimatel = pronajimatele.aktualni(request)
    return pronajimatel.name if pronajimatel else None


def pronajimatel_dropdown(request):
    """Polozky rozbalovatka v hlavicce menu - prepnuti pronajimatele.

    Prave zvoleny se nenabizi, klikat sam na sebe nema smysl. Kdyz je
    pronajimatel jen jeden, vraci prazdny seznam a Unfold rozbalovatko
    vubec nevykresli."""
    from django.urls import reverse

    from core import pronajimatele

    aktualni = pronajimatele.aktualni(request)
    return [
        {
            "title": p.name,
            "icon": "swap_horiz",
            "link": reverse("prepnout_pronajimatele", args=[p.pk]),
        }
        for p in pronajimatele.dostupni()
        if aktualni is None or p.pk != aktualni.pk
    ]


def inline_date_width_fix_css(request):
    from django.templatetags.static import static
    return static("core/css/inline_date_width_fix.css")


def site_icon(request):
    from django.templatetags.static import static
    return static("core/img/logo.svg")


def class_colors_css(request):
    """Dynamicky CSS s barvami textu podle Tridy - viz core.views."""
    from django.urls import reverse
    return reverse("class_colors_css")


def report_filters_css(request):
    from django.templatetags.static import static
    return static("core/css/report_filters.css")


def changelist_header_wrap_css(request):
    from django.templatetags.static import static
    return static("core/css/changelist_header_wrap.css")


def buttons_css(request):
    from django.templatetags.static import static
    return static("core/css/buttons.css")


def sidebar_extras_css(request):
    from django.templatetags.static import static
    return static("core/css/sidebar_extras.css")


def planky_css(request):
    from django.templatetags.static import static
    return static("core/css/planky.css")


def odkazy_css(request):
    from django.templatetags.static import static
    return static("core/css/odkazy.css")


def sekce_css(request):
    from django.templatetags.static import static
    return static("core/css/sekce.css")
