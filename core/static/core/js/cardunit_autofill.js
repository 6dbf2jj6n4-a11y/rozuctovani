/*
1) Pri vyberu plochy (Unit) v inline "Plochy a najemne" automaticky
   vyplni vymeru ze zasobniku (pokud uzivatel nezadal vlastni hodnotu).
2) Pri zmene vymery nebo ceny zive prepocita "Najemne/rok" a
   "Najemne/mesic" pro dany radek.
3) Pod tabulkou zobrazi soucet za vsechny radky.

Pouziva django.jQuery kvuli kompatibilite se select2 (autocomplete).
*/
(function () {
    function parseNum(value) {
        if (!value) {
            return null;
        }
        var n = parseFloat(String(value).replace(",", "."));
        return isNaN(n) ? null : n;
    }

    function formatKc(value) {
        return value.toLocaleString("cs-CZ", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " Kč";
    }

    function getRowArea($row) {
        var $override = $row.find('input[id$="-area_m2_override"]');
        var overrideVal = parseNum($override.val());
        if (overrideVal !== null) {
            return overrideVal;
        }
        var $readonly = $row.find(".field-vymera_zasobnik p, .field-vymera_zasobnik");
        if ($readonly.length) {
            var text = $readonly.first().text();
            return parseNum(text.replace("m²", ""));
        }
        return null;
    }

    function recalcRow($row) {
        var area = getRowArea($row);
        var $rate = $row.find('input[id$="-rate_per_m2"]');
        var rate = parseNum($rate.val());

        var $rocni = $row.find(".field-rocni_najem p, .field-rocni_najem");
        var $mesicni = $row.find(".field-mesicni_najem p, .field-mesicni_najem");

        if (area !== null) {
            $row.attr("data-area", area);
        } else {
            $row.removeAttr("data-area");
        }

        if (area !== null && rate !== null) {
            var rocniVal = area * rate;
            var mesicniVal = rocniVal / 12;
            if ($rocni.length) {
                $rocni.first().text(formatKc(rocniVal));
            }
            if ($mesicni.length) {
                $mesicni.first().text(formatKc(mesicniVal));
            }
            $row.attr("data-rocni-najem", rocniVal);
            $row.attr("data-mesicni-najem", mesicniVal);
        } else {
            $row.removeAttr("data-rocni-najem");
            $row.removeAttr("data-mesicni-najem");
        }
    }

    function recalcTotals($container) {
        var sumRocni = 0;
        var sumMesicni = 0;
        var sumArea = 0;
        $container.find("tr").each(function () {
            var rocni = parseFloat($(this).attr("data-rocni-najem"));
            var mesicni = parseFloat($(this).attr("data-mesicni-najem"));
            var area = parseFloat($(this).attr("data-area"));
            if (!isNaN(rocni)) {
                sumRocni += rocni;
            }
            if (!isNaN(mesicni)) {
                sumMesicni += mesicni;
            }
            if (!isNaN(area)) {
                sumArea += area;
            }
        });

        var $totals = $container.find(".cardunit-totals");
        if ($totals.length === 0) {
            $totals = $(
                '<div class="cardunit-totals" style="margin:8px 0; padding:8px 12px; font-weight:600;"></div>'
            );
            $container.append($totals);
        }
        var areaText = sumArea.toLocaleString("cs-CZ", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " m²";
        $totals.html(
            "Součet výměr: " + areaText +
            " &nbsp;&nbsp; Součet nájemné/rok: " + formatKc(sumRocni) +
            " &nbsp;&nbsp; Součet nájemné/měsíc: " + formatKc(sumMesicni)
        );
    }

    function findContainer($select) {
        var $table = $select.closest("table");
        if ($table.length) {
            return $table.parent();
        }
        var $group = $select.closest('div[id$="-group"]');
        if ($group.length) {
            return $group;
        }
        return $select.closest("fieldset");
    }

    function attach($) {
        // Autofill vymery pri vyberu plochy
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
                    recalcRow($row);
                    recalcTotals(findContainer($select));
                })
                .catch(function () {
                    /* ticho */
                });
        });

        // Zivy prepocet pri editaci vymery nebo ceny
        $(document).on(
            "input change",
            'input[id$="-area_m2_override"], input[id$="-rate_per_m2"]',
            function () {
                var $input = $(this);
                var $row = $input.closest("tr");
                if ($row.length === 0) {
                    return;
                }
                recalcRow($row);
                recalcTotals(findContainer($row.find('select[id$="-unit"]')));
            }
        );

        // Prepocet souctu i pri smazani radku (zaskrtnuti DELETE)
        $(document).on("change", 'input[id$="-DELETE"]', function () {
            var $row = $(this).closest("tr");
            if ($row.length === 0) {
                return;
            }
            if ($(this).is(":checked")) {
                $row.removeAttr("data-rocni-najem");
                $row.removeAttr("data-mesicni-najem");
                $row.removeAttr("data-area");
            } else {
                recalcRow($row);
            }
            recalcTotals(findContainer($row.find('select[id$="-unit"]')));
        });

        // Pocatecni vypocet po nacteni stranky
        $(function () {
            $('select[id$="-unit"]').first().each(function () {
                var $container = findContainer($(this));
                $container.find("tr").each(function () {
                    recalcRow($(this));
                });
                recalcTotals($container);
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
