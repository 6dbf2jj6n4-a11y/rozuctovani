/*
Tlacitko "Nacist z ARES" vedle pole ICO na formulari klienta.
Po kliknuti:
1. Zkontroluje jestli klient s timto ICO uz existuje v databazi
2. Zavola ARES API a automaticky vyplni formular
*/
(function () {
    var $ = (window.django && window.django.jQuery) || window.jQuery;
    if (!$) {
        return;
    }

    function addAresButton() {
        var $ico = $("#id_ico");
        if ($ico.length === 0 || $ico.data("ares-init")) {
            return;
        }
        $ico.data("ares-init", true);

        var $btn = $(
            '<button type="button" id="ares-btn" style="' +
            'margin-left:8px; padding:4px 12px; border-radius:6px; ' +
            'background:#2563eb; color:white; font-weight:600; ' +
            'border:none; cursor:pointer; font-size:13px;">' +
            'Načíst z ARES</button>'
        );

        var $status = $('<span id="ares-status" style="margin-left:8px; font-size:13px;"></span>');

        $ico.after($status).after($btn);

        $btn.on("click", function () {
            var ico = $ico.val().trim().replace(/\s/g, "");
            if (!ico) {
                $status.text("Zadejte IČO.").css("color", "red");
                return;
            }

            $btn.prop("disabled", true).text("Načítám...");
            $status.text("").css("color", "");

            // Nejdrive zkontrolujeme jestli klient uz existuje
            fetch("/admin/core/client/ico-lookup/?ico=" + ico)
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.exists) {
                        $status.html(
                            '⚠ Klient s tímto IČO již existuje: <a href="' +
                            data.url + '" target="_blank">' + data.name + '</a>'
                        ).css("color", "orange");
                        $btn.prop("disabled", false).text("Načíst z ARES");
                        return;
                    }
                    // Klient neexistuje - nacist z ARES
                    return fetch("https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/" + ico)
                        .then(function (r) {
                            if (!r.ok) {
                                throw new Error("Firma nenalezena (status " + r.status + ")");
                            }
                            return r.json();
                        })
                        .then(function (data) {
                            if (data.obchodniJmeno) {
                                $("#id_name").val(data.obchodniJmeno);
                            }
                            if (data.dic) {
                                $("#id_dic").val(data.dic);
                                $("#id_vat_payer").prop("checked", true);
                            }
                            var sidlo = data.sidlo;
                            if (sidlo) {
                                if (sidlo.nazevUlice) {
                                    $("#id_street").val(sidlo.nazevUlice);
                                } else if (sidlo.nazevObce) {
                                    $("#id_street").val(sidlo.nazevObce);
                                }
                                if (sidlo.cisloDomovni) {
                                    var cislo = sidlo.cisloDomovni;
                                    if (sidlo.cisloOrientacni) {
                                        cislo += "/" + sidlo.cisloOrientacni;
                                    }
                                    $("#id_street_number").val(cislo);
                                }
                                if (sidlo.psc) {
                                    $("#id_zip_code").val(String(sidlo.psc));
                                }
                                if (sidlo.nazevObce) {
                                    $("#id_city").val(sidlo.nazevObce);
                                }
                            }
                            $status.text("✓ Načteno z ARES").css("color", "green");
                            $btn.prop("disabled", false).text("Načíst z ARES");
                        });
                })
                .catch(function (err) {
                    $status.text("✗ " + err.message).css("color", "red");
                    $btn.prop("disabled", false).text("Načíst z ARES");
                });
        });
    }

    $(function () {
        addAresButton();
    });
})();
