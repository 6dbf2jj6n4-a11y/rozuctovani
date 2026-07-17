/*
V inline "Klíče" (AllocationKey) na Kartě klienta:
Pri vyberu polozky Zasobniku (service_item) v radku klice se, pokud
radek jeste nema vybrany Typ rozpoctu, automaticky predvyplni z pole
"Vychozi typ rozpoctu" (default_allocation_type) dane polozky.
Nikdy neprepisuje jiz zvoleny typ (napr. u existujiciho klice).
*/
(function () {
    var $ = (window.django && window.django.jQuery) || window.jQuery;
    if (!$) {
        return;
    }

    function getRowAllocationTypeSelect($row) {
        return $row.find('select[id$="-allocation_type"]');
    }

    function applyDefault($row, defaultType) {
        if (!defaultType) {
            return;
        }
        var $typeSelect = getRowAllocationTypeSelect($row);
        if ($typeSelect.length === 0) {
            return;
        }
        if ($typeSelect.val()) {
            // radek uz ma typ zvoleny - neprepisovat
            return;
        }
        $typeSelect.val(defaultType).trigger("change");
    }

    $(document).on("select2:select change", 'select[id$="-service_item"]', function () {
        var $select = $(this);
        var $row = $select.closest("tr");
        if ($row.length === 0) {
            return;
        }
        var itemId = $select.val();
        if (!itemId) {
            return;
        }
        fetch("/admin/core/servicepoolitem/class-lookup/" + itemId + "/")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                applyDefault($row, data.default_allocation_type);
            })
            .catch(function () {
                /* ticho */
            });
    });
})();
