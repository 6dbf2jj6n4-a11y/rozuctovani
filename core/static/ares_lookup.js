/*
Tlacitko "Nacist z ARES" vedle pole ICO na formulari klienta.
Po kliknuti zavola ARES API a automaticky vyplni:
- Nazev firmy, ulici, cislo, PSC, mesto, DIC
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

            fetch("https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/" + ico)
                .then(function (r) {
                    if (!r.ok) {
                        throw new Error("Firma nenalezena (status " + r.status + ")");
                    }
                    return r.json();
                })
                .then(function (data) {
                    // Nazev
                    if (data.obchodniJmeno) {
                        $("#id_name").val(data.obchodniJmeno);
                    }

                    // DIC
                    if (data.dic) {
                        $("#id_dic").val(data.dic);
                    }

                    // Adresa sidla
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

                    // Platce DPH
                    if (data.dic) {
                        $("#id_vat_payer").prop("checked", true);
                    }

                    $status.text("✓ Načteno z ARES").css("color", "green");
                    $btn.prop("disabled", false).text("Načíst z ARES");
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
