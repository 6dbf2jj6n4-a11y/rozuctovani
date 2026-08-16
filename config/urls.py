from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import include, path
from django.views.static import serve as static_serve

from core.views import class_colors_css


@login_required
def home(request):
    """Jedina vstupni adresa (LOGIN_REDIRECT_URL sem posila po prihlaseni) -
    dal rozhodne podle role, kam uzivatele poslat: klient na svoje
    vyuctovani, spravce na zadavani odectu, admin do Django adminu."""
    from accounts.models import User

    role = request.user.role
    if role == User.Role.KLIENT:
        return redirect("moje-vyuctovani")
    if role == User.Role.ADMIN and request.user.is_staff:
        return redirect("admin:index")
    # Spravce, nebo Admin bez zaskrtnuteho Staff statusu (jinak by ho
    # Django admin odrazil zpet na /admin/login/, kde nekdy pada sablona
    # - viz konverzace s Danielem 2026-08-06) - odecty fungujou pro obe role.
    return redirect("odecty")


@staff_member_required
def protected_media(request, path):
    """Media (napr. nahrane/vygenerovane smlouvy) obsahuji citlive udaje
    o klientech - servirovat jen prihlasenym staff uzivatelum, ne verejne."""
    return static_serve(request, path, document_root=settings.MEDIA_ROOT)


urlpatterns = [
    path("", home, name="home"),
    # Zamerne MIMO /admin/ - NonStaffAdminRedirectMiddleware presmerovava
    # vsechny /admin/... adresy neprihlasenych na login, coz by u <link
    # rel=stylesheet> znamenalo 302 misto CSS. Barvy tříd nejsou citlivy
    # udaj, takze nemusi byt za prihlasenim.
    path("barvy-trid.css", class_colors_css, name="class_colors_css"),
    path("admin/", admin.site.urls),
    path("api/", include("billing.api_urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("vyuctovani/", include("billing.urls")),
    path("odecty/", include("meters.urls")),
    path("media/<path:path>", protected_media, name="protected_media"),
]
