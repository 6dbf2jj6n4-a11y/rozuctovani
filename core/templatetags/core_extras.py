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


@register.simple_tag(takes_context=True)
def posledni_akce_v_kontextu(context, pocet=10):
    """Posledni akce uzivatele omezene na zvoleneho pronajimatele.

    Vestavene {% get_admin_log %} ukazuje historii bez ohledu na kontext,
    takze v kontextu DV svitily karty z FM - a jejich odkaz vedl na
    stranku, kterou uzivatel ve zvolenem kontextu stejne neotevre.

    Prislusnost se overuje pres get_queryset prislusneho ModelAdminu, tedy
    stejnym pravidlem jako seznamy (core.admin.PodlePronajimatele) - jeden
    dotaz na kazdy typ objektu v historii, ne na kazdy radek. Zaznamy
    o SMAZANI vypadnou: objekt uz neexistuje, takze se nema jak zaradit.
    """
    from django.contrib import admin as dj
    from django.contrib.admin.models import LogEntry

    from core.admin import PodlePronajimatele

    request = context.get("request")
    if request is None or not request.user.is_authenticated:
        return []

    # Se zapasem nabereme vic radku, nez kolik jich chceme ukazat - cast
    # jich filtr zahodi.
    zaznamy = list(
        LogEntry.objects.filter(user=request.user)
        .select_related("content_type")[: pocet * 5]
    )
    podle_typu = {}
    for z in zaznamy:
        podle_typu.setdefault(z.content_type_id, set()).add(z.object_id)

    povolene = {}
    for typ_id, ids in podle_typu.items():
        typ = next(z.content_type for z in zaznamy if z.content_type_id == typ_id)
        model = typ.model_class()
        spravce = dj.site._registry.get(model) if model else None
        if spravce is None:
            povolene[typ_id] = set()
        elif isinstance(spravce, PodlePronajimatele):
            povolene[typ_id] = {
                str(pk) for pk in spravce.get_queryset(request)
                .filter(pk__in=[i for i in ids if str(i).isdigit()])
                .values_list("pk", flat=True)
            }
        else:
            povolene[typ_id] = set(ids)  # sdilene ciselniky (Obdobi, Tridy...)

    return [
        z for z in zaznamy
        if not z.is_deletion() and z.object_id in povolene.get(z.content_type_id, set())
    ][:pocet]
