"""Sdilene uzpravy admin.ModelAdmin/TabularInline pouzivane napric
core/admin.py a accounts/admin.py."""
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.urls import reverse
from unfold.admin import ModelAdmin as UnfoldModelAdmin, TabularInline as UnfoldTabularInline


def _strip_related_widget_icons(formfield):
    """Vypne ikonky pridat/upravit/nahled/smazat vedle FK/M2M poli
    (Django je pridava automaticky pres RelatedFieldWidgetWrapper) -
    zabiraly misto u poli, ktera uz maji vlastni vyhledavaci
    autocomplete a otevreni/uprava souvisejiciho zaznamu jde stejne
    snadno primo z jeho vlastni stranky v adminu."""
    widget = getattr(formfield, "widget", None)
    if isinstance(widget, RelatedFieldWidgetWrapper):
        widget.can_add_related = False
        widget.can_change_related = False
        widget.can_view_related = False
        widget.can_delete_related = False
    return formfield


class NoRelatedWidgetIconsMixin:
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Django zabaluje FK/M2M pole do RelatedFieldWidgetWrapper az tady
        (v BaseModelAdmin.formfield_for_dbfield), ne uvnitr
        formfield_for_foreignkey/formfield_for_manytomany - proto se to
        musi resit tady, jinak by preprava prisla driv, nez se widget
        vubec zabali."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        return _strip_related_widget_icons(formfield)


class PrevNextNavigationMixin:
    """Prida sipky Předchozí/Další na formular zaznamu, pro pohyb mezi
    zaznamy bez navratu na seznam - poradi stejne jako v seznamu (podle
    get_ordering/Meta.ordering). Sablona: admin/prev_next_change_form.html
    (rozsiruje admin/change_form.html a doplnuje sipky do
    object-tools-items - clientcard/change_form.html na ni napojuje
    svoje tlacitka Kopie stejnym zpusobem).

    change_form_template je tu SEZNAM (ne jeden pevny nazev) - kopiruje
    poradi, ktere by si Django vygeneroval samo (nejdriv model-specificka
    sablona, pak app-specificka), jen s poslednim clankem prohozenym za
    nasi verzi s sipkami misto holeho "admin/change_form.html". Kdyby to
    byl pevny string, Django by uz vubec nehledal
    admin/core/clientcard/change_form.html (viz jeho vlastni Kopie
    tlacitka) - se seznamem se pouzije prvni existujici soubor, presne
    jako v puvodnim chovani."""

    @property
    def change_form_template(self):
        opts = self.model._meta
        return [
            f"admin/{opts.app_label}/{opts.model_name}/change_form.html",
            f"admin/{opts.app_label}/change_form.html",
            "admin/prev_next_change_form.html",
        ]

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        try:
            current_pk = self.model._meta.pk.to_python(object_id)
            pks = list(self.get_queryset(request).values_list("pk", flat=True))
            idx = pks.index(current_pk)
        except (ValueError, TypeError):
            idx = None
        if idx is not None:
            # Absolutni URL pres reverse() - relativni "../{pk}/change/"
            # se spatne rozresi, kdyz uz je v URL cesty za ID jeste neco
            # navic (napr. popup s ?_to_field=...), Django sam pro
            # podobne odkazy (Historie apod.) taky pouziva absolutni cesty.
            opts = self.model._meta
            url_name = f"admin:{opts.app_label}_{opts.model_name}_change"
            if idx > 0:
                extra_context["nav_previous_url"] = reverse(url_name, args=[pks[idx - 1]])
            if idx < len(pks) - 1:
                extra_context["nav_next_url"] = reverse(url_name, args=[pks[idx + 1]])
        return super().change_view(request, object_id, form_url, extra_context)


class ModelAdmin(PrevNextNavigationMixin, NoRelatedWidgetIconsMixin, UnfoldModelAdmin):
    # Unfoldova vestavena funkce (warn_unsaved_form=False je jeji vychozi
    # hodnota) - pri odchodu ze zmeneneho formulare (vc. kliknuti na sipky
    # Předchozí/Další, ktere jsou obycejne <a href> odkazy) vyvola
    # nativni "opustit stranku bez ulozeni?" potvrzeni prohlizece
    # (window.beforeunload). Zapnuto globalne pro cely admin.
    warn_unsaved_form = True


class TabularInline(NoRelatedWidgetIconsMixin, UnfoldTabularInline):
    pass
