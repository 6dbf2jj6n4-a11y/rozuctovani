/*
V inline "Vychozi sluzby plochy" (UnitService):
1) Pole "Mericí" se prevede na plnohodnotny vyhledavaci select2,
   ktery hleda pres vlastni endpoint /admin/core/meter/search/.
2) Vysledky se omezuji na arealu prave editovane Plochy (cteno
   primo z hlavniho formulare - pole "site") a na tridu (typ)
   prave vybrane sluzby v tomtez radku.
3) Pri zmene sluzby v radku se aktualni vyber mericí zrusi (protoze
   pro jinou tridu sluzby uz nemusi davat smysl) a JS si pri dalsim
   vyhledavani vyzada uz jen mericí spravne tridy.
*/
(function () {
    var $ = (window.django && window.django.jQuery) || window.jQuery;
    if (!$) {
        return;
    }

    function getSiteId() {
        var $site = $("#id_site");
        return $site.length ? $site.val() : null;
    }

    function initMeterSelect2($select, meterType) {
        if ($select.data("select2")) {
            $select.select2("destroy");
        }
        $select.select2({
            width: "style",
            allowClear: true,
            placeholder: "Vyhledat měřidlo…",
            ajax: {
                url: "/admin/core/meter/search/",
                dataType: "json",
                delay: 250,
                data: function (params) {
                    return {
                        term: params.term || "",
                        site_id: getSiteId(),
                        meter_type: $select.data("current-meter-type") || meterType || "",
                    };
                },
                processResults: function (data) {
                    return data;
                },
            },
            minimumInputLength: 0,
        });
    }

    function getRowMeterSelect($row) {
        return $row.find('select[id$="-meter"]');
    }

    function updateRowMeterType($row, invoiceClass) {
        var $meterSelect = getRowMeterSelect($row);
        if ($meterSelect.length === 0) {
            return;
        }
        var previousType = $meterSelect.data("current-meter-type");
        $meterSelect.data("current-meter-type", invoiceClass || "");

        if (!$meterSelect.data("select2")) {
            initMeterSelect2($meterSelect, invoiceClass);
        } else if (previousType !== invoiceClass) {
            // trida sluzby se zmenila - puvodni vyber uz nemusi sedet, vycistit
            $meterSelect.val(null).trigger("change.select2");
        }
    }

    $(document).on("select2:select change", 'select[id$="-service_item"]', function () {
        var $select = $(this);
        var $row = $select.closest("tr");
        if ($row.length === 0) {
            return;
        }
        var itemId = $select.val();
        if (!itemId) {
            updateRowMeterType($row, "");
            return;
        }
        fetch("/admin/core/servicepoolitem/class-lookup/" + itemId + "/")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                updateRowMeterType($row, data.invoice_class);
            })
            .catch(function () {
                /* ticho */
            });
    });

    // Inicializace pri nacteni stranky - pro kazdy existujici radek
    $(function () {
        $('select[id$="-service_item"]').each(function () {
            var $select = $(this);
            var $row = $select.closest("tr");
            if ($row.length === 0) {
                return;
            }
            var itemId = $select.val();
            if (!itemId) {
                initMeterSelect2(getRowMeterSelect($row), "");
                return;
            }
            fetch("/admin/core/servicepoolitem/class-lookup/" + itemId + "/")
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    var $meterSelect = getRowMeterSelect($row);
                    $meterSelect.data("current-meter-type", data.invoice_class || "");
                    initMeterSelect2($meterSelect, data.invoice_class);
                })
                .catch(function () {
                    initMeterSelect2(getRowMeterSelect($row), "");
                });
        });
    });
})();
