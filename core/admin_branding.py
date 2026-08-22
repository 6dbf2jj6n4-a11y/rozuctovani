"""Dynamicke doplnky pro Unfold branding (config.settings.UNFOLD) - v samostatnem
modulu, aby settings.py mohl na SITE_SUBHEADER odkazovat jako na retezec
("core.admin_branding.site_subheader"), ktery Unfold importuje az za behu
pozadavku (ne pri startu Django), takze neni problem s poradim inicializace
aplikaci."""


def site_subheader(request):
    from core.models import Client
    landlord = Client.objects.filter(is_landlord=True).first()
    return landlord.name if landlord else None


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
