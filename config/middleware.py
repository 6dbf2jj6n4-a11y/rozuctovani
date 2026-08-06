from django.shortcuts import redirect


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
