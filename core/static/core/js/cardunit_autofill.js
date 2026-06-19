/*
Pri vyberu plochy (Unit) v inline "Plochy a najemne" automaticky
vyplni pole "Vymera (m2) - uprava" hodnotou z zasobniku (Unit.area_m2),
pokud je pole prazdne (aby se neprepisovaly rucni upravy).

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
            var $areaInput = $row.find('input[id$="-area_m2_override"]');
            if ($areaInput.length === 0 || $areaInput.val()) {
                return;
            }
            var unitId = $select.val();
            if (!unitId) {
                return;
            }
            fetch("/admin/core/unit/area-lookup/" + unitId + "/")
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    if (data.area !== null && data.area !== undefined) {
                        $areaInput.val(data.area);
                    }
                })
                .catch(function () {
                    /* ticho - pokud lookup selze, pole jednoduse zustane prazdne */
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
