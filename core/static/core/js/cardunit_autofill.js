/*
1) Pri vyberu plochy (Unit) v inline "Plochy a najemne" automaticky
   vyplni vymeru ze zasobniku (pokud uzivatel nezadal vlastni hodnotu).
2) Pri zmene vymery nebo ceny zive prepocita "Najemne/rok" a
   "Najemne/mesic" pro dany radek.
3) Pod tabulkou zobrazi soucet za vsechny radky.

Pouziva django.jQuery kvuli kompatibilite se select2 (autocomplete).
Promenna $ je definovana JEDNOU na zacatku a sdilena vsemi funkcemi
pres uzaver (closure) - predchozi verze mela chybu, kdy nekterre
pomocne funkce pouzivaly $ bez pristupu k nemu.

Selektor 'select[id^="id_card_units-"][id$="-unit"]' je zamerne uzsi
nez jen 'select[id$="-unit"]' - AllocationKey ma taky pole "unit"
(Plocha u K_PLOSE pausalu), ktere by jinak stejny selektor zachytilo
i v sekcich Elektrina/Voda/Teplo/Ostatni a vkladalo tam zbytecny
soucet vymer/najemneho, ktery tam nedava smysl.
*/
(function () {
    var $ = (window.django && window.django.jQuery) || window.jQuery;
    if (!$) {
        return;
    }

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

    function findTable($el) {
        return $el.closest("table");
    }

    function getOrCreateTotals($table) {
        var $next = $table.next(".cardunit-totals");
        if ($next.length) {
            return $next;
        }
        var $div = $(
            '<div class="cardunit-totals" style="margin:10px 0; padding:10px 14px; font-weight:600; ' +
            'border:1px solid rgba(0,0,0,0.1); border-radius:6px; background:rgba(0,0,0,0.03);"></div>'
        );
        $table.after($div);
        return $div;
    }

    function recalcTotals($table) {
        if (!$table || $table.length === 0) {
            return;
        }
        var sumRocni = 0;
        var sumMesicni = 0;
        var sumArea = 0;
        $table.find("tbody tr, tr").each(function () {
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

        var $totals = getOrCreateTotals($table);
        var areaText = sumArea.toLocaleString("cs-CZ", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " m²";
        $totals.html(
            "Součet výměr: " + areaText +
            " &nbsp;&nbsp; Součet nájemné/rok: " + formatKc(sumRocni) +
            " &nbsp;&nbsp; Součet nájemné/měsíc: " + formatKc(sumMesicni)
        );
    }

    // Autofill vymery pri vyberu plochy
    $(document).on("select2:select change", 'select[id^="id_card_units-"][id$="-unit"]', function () {
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
                recalcTotals(findTable($select));
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
            recalcTotals(findTable($input));
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
        recalcTotals(findTable($row));
    });

    // Pocatecni vypocet po nacteni stranky pro kazdou tabulku CardUnit inline
    $(function () {
        $('select[id^="id_card_units-"][id$="-unit"]').each(function () {
            var $table = findTable($(this));
            if ($table.length === 0 || $table.data("cardunit-initialized")) {
                return;
            }
            $table.data("cardunit-initialized", true);
            $table.find("tr").each(function () {
                recalcRow($(this));
            });
            recalcTotals($table);
        });
    });
})();
