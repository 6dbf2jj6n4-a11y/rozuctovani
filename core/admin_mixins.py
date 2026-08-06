"""Sdilene uzpravy admin.ModelAdmin/TabularInline pouzivane napric
core/admin.py a accounts/admin.py."""
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
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


class ModelAdmin(NoRelatedWidgetIconsMixin, UnfoldModelAdmin):
    pass


class TabularInline(NoRelatedWidgetIconsMixin, UnfoldTabularInline):
    pass
