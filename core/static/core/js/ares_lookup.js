(function () {
    var $ = (window.django && window.django.jQuery) || window.jQuery;
    if (!$) { return; }

    function currentClientId() {
        var m = window.location.pathname.match(/\/client\/(\d+)\/change\/?/);
        return m ? m[1] : "";
    }

    function fillIfEmpty(selector, value) {
        if (!value) { return; }
        var $field = $(selector);
        if (!$field.val()) { $field.val(value); }
    }

    window.aresLookup = function () {
        var ico = $("#id_ico").val().trim().replace(/\s/g, "");
        var $status = $("#ares-status");

        if (!ico) {
            $status.text("Zadejte IČO.").css("color", "red");
            return;
        }

        $status.text("Načítám...").css("color", "gray");

        var lookupUrl = "/admin/core/client/ico-lookup/?ico=" + ico;
        var excludeId = currentClientId();
        if (excludeId) { lookupUrl += "&exclude_id=" + excludeId; }

        fetch(lookupUrl)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.exists) {
                    $status.html(
                        '⚠ Již existuje: <a href="' + data.url + '" target="_blank">' + data.name + '</a>'
                    ).css("color", "orange");
                    return;
                }
                return fetch("https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/" + ico)
                    .then(function (r) {
                        if (!r.ok) throw new Error("Firma nenalezena");
                        return r.json();
                    })
                    .then(function (d) {
                        fillIfEmpty("#id_name", d.obchodniJmeno);
                        if (d.dic) {
                            fillIfEmpty("#id_dic", d.dic);
                            $("#id_vat_payer").prop("checked", true);
                        }
                        var s = d.sidlo;
                        if (s) {
                            fillIfEmpty("#id_street", s.nazevUlice || s.nazevObce || "");
                            var c = s.cisloDomovni || "";
                            if (s.cisloOrientacni) c += "/" + s.cisloOrientacni;
                            fillIfEmpty("#id_street_number", c);
                            if (s.psc) fillIfEmpty("#id_zip_code", String(s.psc));
                            fillIfEmpty("#id_city", s.nazevObce);
                        }
                        var vrLookup = fetch("https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr/" + ico)
                            .then(function (r) { return r.ok ? r.json() : null; })
                            .then(function (vr) {
                                var zaznam = vr && vr.zaznamy && vr.zaznamy[0];
                                var sz = zaznam && zaznam.spisovaZnacka && zaznam.spisovaZnacka[0];
                                if (sz) {
                                    fillIfEmpty("#id_registry_court", sz.soud);
                                    fillIfEmpty("#id_registry_section", sz.oddil);
                                    if (sz.vlozka) fillIfEmpty("#id_registry_insert", String(sz.vlozka));
                                }
                            })
                            .catch(function () {
                                // Verejny rejstrik nemusi byt dostupny pro vsechny typy
                                // subjektu (napr. OSVC) - jmeno/sidlo uz mame, nevadi.
                            });

                        var dphLookup = fetch("/admin/core/client/dph-lookup/?ico=" + ico)
                            .then(function (r) { return r.json(); })
                            .then(function (dph) {
                                if (!dph.found) { return ""; }
                                var acc = dph.accounts && dph.accounts[0];
                                if (acc) {
                                    fillIfEmpty("#id_bank_account", acc.cislo_uctu);
                                    fillIfEmpty("#id_bank_code", acc.kod_banky);
                                    fillIfEmpty("#id_bank_name", acc.nazev_banky);
                                }
                                return dph.nespolehlivy_platce === "ANO"
                                    ? " ⚠ NESPOLEHLIVÝ PLÁTCE DPH!"
                                    : "";
                            })
                            .catch(function () { return ""; });

                        return Promise.all([vrLookup, dphLookup]).then(function (results) {
                            return results[1] || "";
                        });
                    })
                    .then(function (warning) {
                        $status.text("✓ Načteno z ARES (doplněna jen prázdná pole)" + (warning || "")).css(
                            "color", warning ? "red" : "green"
                        );
                    });
            })
            .catch(function (err) {
                $status.text("✗ " + err.message).css("color", "red");
            });
    };
})();
