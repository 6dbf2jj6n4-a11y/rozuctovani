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
