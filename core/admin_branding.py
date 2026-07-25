"""Dynamicke doplnky pro Unfold branding (config.settings.UNFOLD) - v samostatnem
modulu, aby settings.py mohl na SITE_SUBHEADER odkazovat jako na retezec
("core.admin_branding.site_subheader"), ktery Unfold importuje az za behu
pozadavku (ne pri startu Django), takze neni problem s poradim inicializace
aplikaci."""


def site_subheader(request):
    # DOCASNY DIAGNOSTICKY MARKER - viz konverzace, az potvrdime ze
    # SITE_SUBHEADER mechanismus na produkci vubec funguje, vratime
    # zpet na puvodni dynamicke dohledani Client.is_landlord.
    return "DIAG_MARKER_funguje"
