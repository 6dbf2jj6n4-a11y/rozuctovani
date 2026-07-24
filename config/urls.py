from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import include, path
from django.views.static import serve as static_serve


@staff_member_required
def protected_media(request, path):
    """Media (napr. nahrane/vygenerovane smlouvy) obsahuji citlive udaje
    o klientech - servirovat jen prihlasenym staff uzivatelum, ne verejne."""
    return static_serve(request, path, document_root=settings.MEDIA_ROOT)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("billing.api_urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("vyuctovani/", include("billing.urls")),
    path("media/<path:path>", protected_media, name="protected_media"),
]
