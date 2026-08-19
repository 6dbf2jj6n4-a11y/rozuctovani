from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User as AuthUser
from core.admin_mixins import ModelAdmin
from .models import User

try:
    admin.site.unregister(AuthUser)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class CustomUserAdmin(ModelAdmin, UserAdmin):
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "password1", "password2", "role", "sites", "client"),
        }),
    )
    fieldsets = (
        UserAdmin.fieldsets[0],
        # Fotka patri k osobnim udajum (jmeno, e-mail), proto se pridava
        # do te sekce misto vlastni - viz panel uzivatele dole v menu
        # (templates/unfold/helpers/user_panel.html).
        (
            UserAdmin.fieldsets[1][0],
            {**UserAdmin.fieldsets[1][1],
             "fields": (*UserAdmin.fieldsets[1][1]["fields"], "photo")},
        ),
        ("Role a přístup", {"fields": ("role", "client", "sites")}),
        *UserAdmin.fieldsets[2:],
    )
    list_display = ("nahled_fotky", "username", "email", "role", "client", "is_active")
    list_display_links = ("nahled_fotky", "username")
    list_filter = ("role", "is_active")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Formularovy prvek pro Fotku si u ulozeneho souboru vykresluje
        odkaz "Aktualne: ...", pri kterem sahne na .url. Kdyz je uloziste
        nedostupne (chybna/chybejici konfigurace R2, vypadek), shodilo by
        to celou stranku uzivatele - proto se v takovem pripade tvarime,
        ze soubor nahrany neni, a nabidne se jen pole pro nahrani."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "photo" and formfield is not None:
            def is_initial(value):
                # Pozor: puvodni Djangovo is_initial dela
                # getattr(value, "url", False), coz pohlti jen chybejici
                # atribut - ne chybu uloziste. Proto se nevola vubec.
                try:
                    return bool(value and value.url)
                except Exception:
                    return False

            formfield.widget.is_initial = is_initial
        return formfield

    @admin.display(description="Fotka")
    def nahled_fotky(self, obj):
        """Male kolecko s fotkou primo v seznamu, aby bylo hned videt,
        kdo ji ma. Podepsana URL z R2 plati hodinu, proto se generuje az
        pri zobrazeni (viz User.photo_url a core/storage.py)."""
        from django.utils.html import format_html

        url = obj.photo_url
        if not url:
            return "—"
        return format_html(
            '<img src="{}" alt="" style="width:28px; height:28px; '
            'border-radius:50%; object-fit:cover; display:block;">', url
        )
