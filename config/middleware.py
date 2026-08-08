import logging
import time

from django.db import connection
from django.shortcuts import redirect
from django.test.utils import CaptureQueriesContext

logger = logging.getLogger("perf")


class SlowRequestLoggingMiddleware:
    """Docasna diagnostika: zaloguje cestu, dobu trvani a POCET DB dotazu
    (ne jejich SQL text) pro kazdy pomaly (>1s) request od prihlaseneho
    uzivatele - bez zapnuti plneho SQL logovani, ktere uz bylo vypnuto
    kvuli zahlcovani produkcnich logu (viz DEBUG=0, commit 83fe24c).
    CaptureQueriesContext funguje nezavisle na DEBUG (docasne zapne
    force_debug_cursor jen pro tenhle request). Pouzito k dohledani,
    KTERA stranka dela kolik dotazu - viz konverzace s Danielem,
    stranka "Položky" se nacita >6s bez zjevne pricinny v kodu."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        with CaptureQueriesContext(connection) as ctx:
            response = self.get_response(request)
        duration = time.monotonic() - start
        if duration > 1 and getattr(request, "user", None) and request.user.is_authenticated:
            logger.warning(
                "POMALY REQUEST: %s %s - %.2fs, %d DB dotazu",
                request.method, request.path, duration, len(ctx.captured_queries),
            )
        return response


class NonStaffAdminRedirectMiddleware:
    """Prihlaseny uzivatel bez is_staff, ktery zkusi jakoukoliv /admin/...
    adresu (napr. stara zalozka), by jinak skoncil na /admin/login/ -
    tam ale nekdy pada Unfold sablona (KeyError na 'opts'/'href'/'name'/
    'attrs' v unfold/components/button.html) pro prihlaseneho-ale-ne-
    staff uzivatele, misto hezke chybove hlasky Internal Server Error
    ve smycce. Viz konverzace s Danielem 2026-08-06 (Olda). Presmerujeme
    ho radeji rovnou na jeho domovskou obrazovku, driv nez se ta sablona
    vubec zkusi vykreslit."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path.startswith("/admin/")
            and request.user.is_authenticated
            and not request.user.is_staff
        ):
            return redirect("home")
        return self.get_response(request)
