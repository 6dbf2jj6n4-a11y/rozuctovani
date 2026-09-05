/*
Zivy soucet vytapenych ploch v sekci Teplo (Karta klienta).

Server cislo vykresli z ulozenych dat; tohle doplni prepnuti, ktera
uzivatel jeste neulozil - jinak by po zaskrtnuti "Vytapena" ukazoval
ramecek pod tabulkou stare cislo, dokud se karta neulozi.

Poradi pravidel je STEJNE jako CardUnit.vytapena_plocha na serveru:
nevytapena plocha nic, vyplnena "Vytapena m2" ma prednost pred vymerou,
jinak plati vymera radku. Kdyby se rozeslo, ukazoval by formular jine
cislo, nez kterym se teplo skutecne deli.
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

    function plochaRadku($row) {
        if (!$row.find('input[id$="-unit_is_heated"]').is(":checked")) {
            return 0;
        }
        var vlastni = parseNum($row.find('input[id$="-unit_heated_area_m2"]').val());
        if (vlastni !== null) {
            return vlastni;
        }
        // Vymeru nese radek v data-vymera (sablona ji tam da uz
        // odlokalizovanou, viz cardunit_teplo_inline_tabular.html).
        var vymera = parseNum($row.attr("data-vymera"));
        return vymera === null ? 0 : vymera;
    }

    function prepocti() {
        var $soucet = $("#rx-vytapena-plocha-soucet");
        if ($soucet.length === 0) {
            return;
        }
        var celkem = 0;
        $('input[id$="-unit_is_heated"]').each(function () {
            celkem += plochaRadku($(this).closest("tr"));
        });
        $soucet.text(celkem.toLocaleString("cs-CZ", {
            minimumFractionDigits: 2, maximumFractionDigits: 2,
        }));
        $("#rx-vytapena-plocha-hint").toggle(celkem === 0);
    }

    $(document).on(
        "input change",
        'input[id$="-unit_is_heated"], input[id$="-unit_heated_area_m2"]',
        prepocti
    );
    $(prepocti);
})();
