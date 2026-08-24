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


# Jak daleko dozadu se kouka na aktivitu (v sekundach) - kdo za tuhle
# dobu neposlal zadny pozadavek, uz se za prihlaseneho nepocita.
OKNO_AKTIVITY = 15 * 60


@register.simple_tag(takes_context=True)
def pocet_prihlasenych(context):
    """Kolik RUZNYCH uzivatelu bylo za posledni ctvrthodinu aktivnich -
    cislo v kolecku loga v hlavicce menu (templates/unfold/helpers/
    site_icon.html).

    Diky SESSION_SAVE_EVERY_REQUEST (config/settings.py) prepisuje Django
    radek session pri kazdem pozadavku, takze django_session.expire_date
    je vzdycky "cas posledniho pozadavku + SESSION_COOKIE_AGE". Aktivni
    session se proto pozna bez cteni obsahu: expire_date musi lezet dal
    nez (ted + SESSION_COOKIE_AGE - OKNO_AKTIVITY). Rozsifrovava se pak
    uz jen tahle hrstka radku, aby se z nich vytahlo _auth_user_id -
    jeden clovek muze mit otevreny notebook i telefon a to jsou dve
    session, ale porad jeden uzivatel.

    Prave prihlaseny uzivatel se pricita natvrdo: jeho session se ulozi
    az v process_response, tedy AZ PO vykresleni sablony, takze pri
    prvnim pozadavku po delsi pauze by se sam nezapocital.
    Konverzace s Danielem 2026-08-24."""
    from datetime import timedelta

    from django.conf import settings
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    hranice = timezone.now() + timedelta(
        seconds=settings.SESSION_COOKIE_AGE - OKNO_AKTIVITY
    )
    uzivatele = set()
    for session in Session.objects.filter(expire_date__gt=hranice).only("session_data"):
        uzivatel_id = session.get_decoded().get("_auth_user_id")
        if uzivatel_id:
            uzivatele.add(str(uzivatel_id))

    request = context.get("request")
    if request is not None and request.user.is_authenticated:
        uzivatele.add(str(request.user.pk))

    return len(uzivatele)
