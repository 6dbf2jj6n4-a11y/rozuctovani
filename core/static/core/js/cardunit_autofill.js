/*
Pri vyberu plochy (Unit) v inline "Plochy a najemne" automaticky
vyplni pole "Vymera (m2) - uprava" hodnotou z zasobniku (Unit.area_m2),
pokud je pole prazdne (aby se neprepisovaly rucni upravy), a zaroven
zobrazi hodnotu i v readonly sloupci "Vymera (zasobnik)".

Pouziva django.jQuery, protoze autocomplete pole (select2) generuje
zmenu hodnoty pres jQuery udalosti, ktere nezachyti standardni
document.addEventListener('change', ...).
*/
(function () {
    function attach($) {
        $(document).on("select2:select change", 'select[id$="-unit"]', function () {
            var $select = $(this);
            var $row = $select.closest("tr");
            if ($row.length === 0) {
                return;
            }
            var unitId = $select.val();
            if (!unitId) {
                return;
            }

            var $areaInput = $row.find('input[id$="-area_m2_override"]');
            var $readonlyCell = $row.find(".field-vymera_zasobnik p, .field-vymera_zasobnik");

            fetch("/admin/core/unit/area-lookup/" + unitId + "/")
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    if (data.area === null || data.area === undefined) {
                        return;
                    }
                    if ($areaInput.length && !$areaInput.val()) {
                        $areaInput.val(data.area);
                    }
                    if ($readonlyCell.length) {
                        $readonlyCell.first().text(data.area + " m²");
                    }
                })
                .catch(function () {
                    /* ticho - pokud lookup selze, pole jednoduse zustanou prazdna */
                });
        });
    }

    if (window.django && window.django.jQuery) {
        attach(window.django.jQuery);
    } else if (window.jQuery) {
        attach(window.jQuery);
    } else {
        document.addEventListener("DOMContentLoaded", function () {
            if (window.django && window.django.jQuery) {
                attach(window.django.jQuery);
            }
        });
    }
})();
