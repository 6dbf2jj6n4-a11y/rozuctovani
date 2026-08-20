"""Vlastni popisky v naseptavacich (autocomplete) Django adminu.

Django sklada popisek polozky napevno jako `str(obj)`
(`AutocompleteJsonView.serialize_result`) a endpoint je JEDEN pro cely
admin (`/admin/autocomplete/`, viz `AdminSite.autocomplete_view`) - ne
per model. Metoda `serialize_result` na ModelAdminu se proto NIKDY
nevola; kdo si ji tam napsal, psal mrtvy kod.

Tenhle pohled to napravuje: zepta se ModelAdminu prislusneho modelu na
`autocomplete_label(obj)`, a kdyz ji nema, chova se jako Django.

Zapojeno v config/urls.py cestou, ktera stini `admin/autocomplete/`
(reverse("admin:autocomplete") vraci porad stejnou adresu, jen ji
obslouzi tenhle pohled).

Duvod vzniku: v naseptavaci Podruzneho meridla u Klice byly dve polozky
"E_SPOL" - jedna FM, jedna NJ - a neslo poznat, kterou vybrat. Viz
konverzace s Danielem 2026-08-20.
"""
from django.contrib.admin.views.autocomplete import AutocompleteJsonView


class PopiskyAutocompleteView(AutocompleteJsonView):
    def serialize_result(self, obj, to_field_name):
        vysledek = super().serialize_result(obj, to_field_name)
        popisek = getattr(self.model_admin, "autocomplete_label", None)
        if callable(popisek):
            vysledek["text"] = popisek(obj)
        return vysledek
