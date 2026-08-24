import logging
import re
import time
from collections import Counter

from django.db import connection
from django.shortcuts import redirect
from django.test.utils import CaptureQueriesContext

logger = logging.getLogger("perf")

# Nahradi cisla a retezcove literaly v SQL placeholderem, aby se stejny
# "tvar" dotazu (jen s jinym ID/hodnotou) sloucil do jedne skupiny -
# stejny princip jako "N similar queries" v Django Debug Toolbar.
_SQL_LITERAL_RE = re.compile(r"'[^']*'|\b\d+\b")


def _sql_shape(sql):
    return _SQL_LITERAL_RE.sub("?", sql)[:200]


class SlowRequestLoggingMiddleware:
    """Docasna diagnostika: zaloguje cestu, dobu trvani, POCET DB dotazu
    a NEJCASTEJI OPAKOVANY tvar dotazu (bez konkretnich hodnot, jen
    "kolikrat + jaka tabulka") pro kazdy pomaly (>1s) request od
    prihlaseneho uzivatele - bez zapnuti plneho SQL logovani, ktere uz
    bylo vypnuto kvuli zahlcovani produkcnich logu (viz DEBUG=0, commit
    83fe24c). CaptureQueriesContext funguje nezavisle na DEBUG (docasne
    zapne force_debug_cursor jen pro tenhle request). Pouzito k
    dohledani, KTERY konkretni dotaz se v ramci jednoho requestu
    opakuje N+1 krat - viz konverzace s Danielem, stranka "Položky" dela
    107 dotazu bez zjevne pricinny v kodu (list_select_related uz je
    nastaveny)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        with CaptureQueriesContext(connection) as ctx:
            response = self.get_response(request)
        duration = time.monotonic() - start
        if duration > 1 and getattr(request, "user", None) and request.user.is_authenticated:
            queries = ctx.captured_queries
            shapes = Counter(_sql_shape(q["sql"]) for q in queries)
            top = shapes.most_common(3)
            top_text = " | ".join(f"{count}x {shape}" for shape, count in top)
            logger.warning(
                "POMALY REQUEST: %s %s - %.2fs, %d DB dotazu. NEJCASTEJSI: %s",
                request.method, request.path, duration, len(queries), top_text,
            )
        return response


class NonStaffAdminRedirectMiddleware:
    """Dve situace, kdy by spravce/klient (bez is_staff) nemel skoncit na
    Django adminove VLASTNI prihlasovaci strance (/admin/login/):

    1) PRIHLASENY uzivatel bez is_staff, ktery zkusi jakoukoliv /admin/...
    adresu (napr. stara zalozka), by jinak skoncil na /admin/login/ -
    tam ale nekdy pada Unfold sablona (KeyError na 'opts'/'href'/'name'/
    'attrs' v unfold/components/button.html) pro prihlaseneho-ale-ne-
    staff uzivatele, misto hezke chybove hlasky Internal Server Error
    ve smycce. Viz konverzace s Danielem 2026-08-06 (Olda). Presmerujeme
    ho radeji rovnou na jeho domovskou obrazovku, driv nez se ta sablona
    vubec zkusi vykreslit.

    2) NEPRIHLASENY uzivatel, ktery zkusi /admin/... (typicky /admin/login/
    primo, napr. spatny odkaz/zvyk), skonci na Django adminove
    AdminAuthenticationForm - ta i pri SPRAVNEM hesle odmitne kohokoliv
    bez is_staff s hlaskou "Zadejte spravne uzivatelske jmeno a heslo pro
    personál" (zmatecne pusobi jako spatne heslo, i kdyz je spravne - viz
    konverzace s Danielem 2026-08-09, Olda a David se nemohli prihlasit).
    Presmerujeme na normalni prihlasovaci stranku (/accounts/login/, bez
    is_staff omezeni) se zachovanym 'next', aby po prihlaseni pokracovali
    presne tam, kam meli namireno."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/"):
            if request.user.is_authenticated and not request.user.is_staff:
                return redirect("home")
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path(), login_url="/accounts/login/")
        return self.get_response(request)


class PronajimatelMiddleware:
    """Do adminu se nedostaneme bez zvoleneho pronajimatele.

    Aplikace vede data vic pronajimatelu v jedne databazi, ale pracuje se
    vzdycky s jednim - dokud si uzivatel nezvoli, se kterym, nema smysl mu
    ukazovat seznamy, ktere by michaly obe osoby dohromady. Kdyz je
    pronajimatel jen jeden, zvoli se sam a uzivatel o tehle vrstve vubec
    nevi.

    Hlida se jen /admin/ - zadavani odectu (/odecty/) ma vlastni omezeni
    pres accounts.User.sites a klientske vyuctovani se pronajimatele
    netyka. Viz core/pronajimatele.py, konverzace s Danielem 2026-08-25.
    """

    # Adresy, ktere musi projit i bez volby, jinak by vzniklo presmerovaci
    # kolecko (sama volba) nebo by se uzivatel nemohl odhlasit.
    VOLNE = ("/admin/pronajimatel/", "/admin/logout/", "/admin/login/", "/admin/jsi18n/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path.startswith("/admin/")
            and not request.path.startswith(self.VOLNE)
            and request.user.is_authenticated
            and request.user.is_staff
        ):
            from django.shortcuts import redirect
            from django.urls import reverse
            from django.utils.http import urlencode

            from core import pronajimatele

            if pronajimatele.aktualni(request) is None:
                dostupni = list(pronajimatele.dostupni())
                if len(dostupni) == 1:
                    pronajimatele.nastav(request, dostupni[0])
                else:
                    return redirect("{}?{}".format(
                        reverse("vyber_pronajimatele"),
                        urlencode({"dal": request.get_full_path()}),
                    ))
        return self.get_response(request)
