(function () {
    var $ = (window.django && window.django.jQuery) || window.jQuery;
    if (!$) { return; }

    window.aresLookup = function () {
        var ico = $("#id_ico").val().trim().replace(/\s/g, "");
        var $status = $("#ares-status");

        if (!ico) {
            $status.text("Zadejte IČO.").css("color", "red");
            return;
        }

        $status.text("Načítám...").css("color", "gray");

        fetch("/admin/core/client/ico-lookup/?ico=" + ico)
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
                        if (d.obchodniJmeno) $("#id_name").val(d.obchodniJmeno);
                        if (d.dic) { $("#id_dic").val(d.dic); $("#id_vat_payer").prop("checked", true); }
                        var s = d.sidlo;
                        if (s) {
                            $("#id_street").val(s.nazevUlice || s.nazevObce || "");
                            var c = s.cisloDomovni || "";
                            if (s.cisloOrientacni) c += "/" + s.cisloOrientacni;
                            $("#id_street_number").val(c);
                            if (s.psc) $("#id_zip_code").val(String(s.psc));
                            if (s.nazevObce) $("#id_city").val(s.nazevObce);
                        }
                        $status.text("✓ Načteno z ARES").css("color", "green");
                    });
            })
            .catch(function (err) {
                $status.text("✗ " + err.message).css("color", "red");
            });
    };
})();
