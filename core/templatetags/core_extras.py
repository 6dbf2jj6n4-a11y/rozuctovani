from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_if_exists(path):
    """Vrati static URL jen kdyz soubor v projektu skutecne existuje -
    jinak None. Bez tohohle by {% static %} na produkci (ManifestStatic
    FilesStorage) vyhodilo ValueError a spadla by cela stranka, kdyby
    soubor jeste nebyl pribaleny (napr. avatar, ktery ma Daniel jeste
    dodat) - viz konverzace 2026-08-18."""
    if finders.find(path):
        return static(path)
    return None
