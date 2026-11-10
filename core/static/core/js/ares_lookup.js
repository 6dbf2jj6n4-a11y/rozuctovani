(function () {
    var $ = (window.django && window.django.jQuery) || window.jQuery;
    if (!$) { return; }

    function currentClientId() {
        var m = window.location.pathname.match(/\/client\/(\d+)\/change\/?/);
        return m ? m[1] : "";
    }

    // ARES vraci soud jen jako zkratku (napr. "KSOS") - obchodni rejstrik
    // v CR vede jen techto 8 soudu, mapa je tedy uzavrena a stabilni.
    var COURT_NAMES = {
        MSPH: "Městský soud v Praze",
        KSPH: "Krajský soud v Praze",
        KSCB: "Krajský soud v Českých Budějovicích",
        KSPL: "Krajský soud v Plzni",
        KSUL: "Krajský soud v Ústí nad Labem",
        KSHK: "Krajský soud v Hradci Králové",
        KSBR: "Krajský soud v Brně",
        KSOS: "Krajský soud v Ostravě",
    };

    function courtName(code) {
        if (!code) { return code; }
        return COURT_NAMES[code] || code;
    }

    // [ulice, cislo] ze sidla - stejne pravidlo jako ulice_a_cislo() v
    // core/ares_client.py. ARES (API 1.3) u casti adres nevyplni nazevUlice
    // ani cisloOrientacni, ulice je pak jen v textovaAdresa
    // ("Vitkovicka 3335/15, ..."); obec bez ulic ma v textu cast obce
    // ("Liskovec 393") nebo jen "c.p. 256".
    function uliceACislo(s) {
        var ulice = s.nazevUlice || "";
        var cislo = String(s.cisloDomovni || "");
        var orientacni = String(s.cisloOrientacni || "") + (s.cisloOrientacniPismeno || "");
        if (orientacni) cislo += "/" + orientacni;
        if (ulice) return [ulice, cislo];

        var prvni = (s.textovaAdresa || "").split(",")[0].trim();
        var m = prvni.match(/^(.+?)\s+(\d+[A-Za-z]?(?:\/\d+[A-Za-z]?)?)$/);
        if (m) {
            ulice = /^[čc]\./i.test(m[1]) ? "" : m[1];  // č.p. / č.ev.
            cislo = m[2];
        }
        return [ulice || s.nazevCastiObce || s.nazevObce || "", cislo];
    }

    // Obec v postovnim tvaru z textove adresy ("..., 10100 Praha 10") -
    // nazevObce je u Prahy jen "Praha", my mame "Praha 10". Stejne
    // pravidlo je v core/ares_client.py (obec). Daniel 2026-11-10.
    function obec(s) {
        var m = (s.textovaAdresa || "").match(/\b\d{3}\s?\d{2}\s+([^,]+)$/);
        return m ? m[1].trim() : (s.nazevObce || "");
    }

    // Platna spisova znacka. ARES vraci celou historii vcetne vymazanych
    // (GEHER GEO: KSBR vymazana 2020 je v poli PRVNI, platna je KSOS),
    // platna je ta bez datumVymazu. Stejne pravidlo je v
    // core/ares_client.py (platna_spisova_znacka).
    function platnaSpisovaZnacka(vr) {
        var zaznamy = (vr && vr.zaznamy) || [];
        var zaznam = zaznamy.filter(function (z) { return z.primarniZaznam; })[0] || zaznamy[0];
        var znacky = (zaznam && zaznam.spisovaZnacka) || [];
        var platne = znacky.filter(function (sz) { return !sz.datumVymazu; });
        return platne[platne.length - 1] || null;
    }

    // --- Porovnani s formularem -------------------------------------------
    // Drive se z ARES doplnovala JEN prazdna pole, takze zmenu sidla
    // (GEHER GEO, listopad 2026) aplikace nikdy nezachytila. Ted: prazdna
    // pole se doplni rovnou (nic se tim neztrati), a co se od ARES lisi,
    // se ukaze jako tabulka "ted -> ARES" k potvrzeni. Prepisuje se jen
    // formular - do DB se zmena dostane az tlacitkem Ulozit.
    // Daniel 2026-11-10.

    function text(v) { return String(v == null ? "" : v).replace(/\s+/g, " ").trim(); }
    function bezMezer(v) { return text(v).replace(/\s/g, "").toUpperCase(); }
    function psc(v) {
        var c = text(v).replace(/\s/g, "");
        return /^\d{5}$/.test(c) ? c.slice(0, 3) + " " + c.slice(3) : text(v);
    }
    // 000123-0000456 a 123-456 je tentyz ucet
    function ucet(v) {
        return bezMezer(v).split("-").map(function (cast) {
            return cast.replace(/^0+(?=\d)/, "");
        }).join("-");
    }

    var POLE = {
        name: "Název",
        dic: "DIČ",
        vat_payer: "Plátce DPH",
        street: "Ulice",
        street_number: "Číslo",
        zip_code: "PSČ",
        city: "Město",
        registry_court: "Rejstříkový soud",
        registry_section: "Oddíl",
        registry_insert: "Vložka",
        bank_account: "Číslo účtu",
        bank_code: "Kód banky",
        bank_name: "Banka",
    };

    // navrhy: [{pole, hodnota, porovnat}] -> doplni prazdna, vrati rozdilna
    function roztridit(navrhy) {
        var doplneno = [];
        var zmeny = [];
        navrhy.forEach(function (n) {
            var hodnota = text(n.hodnota);
            if (!hodnota) { return; }
            var $f = $("#id_" + n.pole);
            if (!$f.length) { return; }
            var ted = text($f.val());
            if (!ted) {
                $f.val(hodnota).trigger("change");
                doplneno.push(POLE[n.pole]);
                return;
            }
            var stejne = n.porovnat ? n.porovnat(ted) === n.porovnat(hodnota) : ted === hodnota;
            if (!stejne) {
                zmeny.push({ pole: n.pole, ted: ted, hodnota: hodnota });
            }
        });
        return { doplneno: doplneno, zmeny: zmeny };
    }

    function esc(v) { return $("<div>").text(v).html(); }

    function zobrazitZmeny(zmeny, $status, hlaska) {
        $("#ares-zmeny").remove();
        if (!zmeny.length) { return; }

        var radky = zmeny.map(function (z, i) {
            var ted = z.pole === "vat_payer" ? (z.ted ? "ano" : "ne") : z.ted;
            var nove = z.pole === "vat_payer" ? (z.hodnota ? "ano" : "ne") : z.hodnota;
            return '<tr style="border-top:1px solid rgba(127,127,127,.25);">'
                + '<td style="padding:6px 8px;"><input type="checkbox" checked data-i="' + i + '"></td>'
                + '<td style="padding:6px 8px; font-weight:600;">' + esc(POLE[z.pole]) + '</td>'
                + '<td style="padding:6px 8px; text-decoration:line-through; opacity:.7;">' + esc(ted) + '</td>'
                + '<td style="padding:6px 8px; font-weight:600;">' + esc(nove) + '</td>'
                + '</tr>';
        }).join("");

        var $panel = $(
            '<div id="ares-zmeny" style="margin:0 12px 12px; padding:12px; border:1px solid #d97706; border-radius:6px;">'
            + '<div style="font-weight:600; margin-bottom:8px;">ARES má jiné údaje – co převzít?</div>'
            + '<table style="width:100%; max-width:720px; border-collapse:collapse; font-size:13px;">'
            + '<thead><tr style="text-align:left;"><th></th><th style="padding:6px 8px;">Pole</th>'
            + '<th style="padding:6px 8px;">Teď</th><th style="padding:6px 8px;">ARES</th></tr></thead>'
            + '<tbody>' + radky + '</tbody></table>'
            + '<div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">'
            + '<button type="button" class="rx-btn rx-btn-primary" data-akce="prevzit">Převzít vybrané</button>'
            + '<button type="button" class="rx-btn" data-akce="nechat">Nechat beze změny</button>'
            + '</div></div>'
        );

        $panel.on("click", "button", function () {
            var prevzato = 0;
            if ($(this).data("akce") === "prevzit") {
                $panel.find("input[type=checkbox]:checked").each(function () {
                    var z = zmeny[$(this).data("i")];
                    if (z.pole === "vat_payer") {
                        $("#id_vat_payer").prop("checked", z.hodnota).trigger("change");
                    } else {
                        $("#id_" + z.pole).val(z.hodnota).trigger("change");
                    }
                    prevzato++;
                });
            }
            $panel.remove();
            $status.text(
                prevzato
                    ? hlaska + " Převzato změn: " + prevzato + " – nezapomeň Uložit."
                    : hlaska + " Změny z ARES nepřevzaty."
            ).css("color", prevzato ? "#d97706" : "gray");
        });

        // Pod cely radek s IC/DIC/tlacitkem - v bunce tlacitka je na
        // tabulku malo mista.
        var $radek = $status.closest(".form-row");
        if ($radek.length) { $radek.after($panel); } else { $status.after($panel); }
    }

    window.aresLookup = function () {
        var ico = $("#id_ico").val().trim().replace(/\s/g, "");
        var $status = $("#ares-status");
        $("#ares-zmeny").remove();

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
                        '⚠ Již existuje: <a href="' + data.url + '" target="_blank">' + esc(data.name) + '</a>'
                    ).css("color", "orange");
                    return;
                }
                var zaklad = fetch("https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/" + ico)
                    .then(function (r) {
                        if (!r.ok) throw new Error("Firma nenalezena");
                        return r.json();
                    });
                // Verejny rejstrik nemusi byt dostupny pro vsechny typy
                // subjektu (napr. OSVC) - jmeno/sidlo staci, nevadi.
                var rejstrik = fetch("https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr/" + ico)
                    .then(function (r) { return r.ok ? r.json() : null; })
                    .catch(function () { return null; });
                var dph = fetch("/admin/core/client/dph-lookup/?ico=" + ico)
                    .then(function (r) { return r.json(); })
                    .catch(function () { return { found: false }; });

                return Promise.all([zaklad, rejstrik, dph]).then(function (vysledky) {
                    var d = vysledky[0], vr = vysledky[1], reg = vysledky[2];
                    // Nazev bez ohledu na velikost pismen a mezery - u nas
                    // "Dalibor HOLUB" a "s. r. o." (konvence), v ARES
                    // "Dalibor Holub" a "s.r.o."; jinak by se nabizelo
                    // pokazde.
                    var navrhy = [{ pole: "name", hodnota: d.obchodniJmeno, porovnat: function (v) {
                        return v.replace(/\s/g, "").toLowerCase();
                    } }];
                    if (d.dic) {
                        navrhy.push({ pole: "dic", hodnota: d.dic, porovnat: bezMezer });
                    }
                    var s = d.sidlo;
                    if (s) {
                        var adresa = uliceACislo(s);
                        navrhy.push(
                            { pole: "street", hodnota: adresa[0] },
                            { pole: "street_number", hodnota: adresa[1], porovnat: bezMezer },
                            { pole: "zip_code", hodnota: s.psc ? psc(s.psc) : "", porovnat: bezMezer },
                            { pole: "city", hodnota: obec(s) }
                        );
                    }
                    var sz = platnaSpisovaZnacka(vr);
                    if (sz) {
                        navrhy.push(
                            { pole: "registry_court", hodnota: courtName(sz.soud) },
                            { pole: "registry_section", hodnota: sz.oddil, porovnat: bezMezer },
                            { pole: "registry_insert", hodnota: sz.vlozka, porovnat: bezMezer }
                        );
                    }

                    // Ucet: nas se nenavrhuje zmenit, kdyz je mezi
                    // zverejnenymi - firma jich muze mit vic.
                    var ucty = (reg && reg.found && reg.accounts) || [];
                    var nas = ucet($("#id_bank_account").val());
                    var nasKod = bezMezer($("#id_bank_code").val());
                    var zverejneny = ucty.filter(function (a) {
                        return ucet(a.cislo_uctu) === nas && bezMezer(a.kod_banky) === nasKod;
                    })[0];
                    if (zverejneny) {
                        navrhy.push({ pole: "bank_name", hodnota: zverejneny.nazev_banky, porovnat: function () { return ""; } });
                    } else if (ucty.length) {
                        navrhy.push(
                            { pole: "bank_account", hodnota: ucty[0].cislo_uctu, porovnat: ucet },
                            { pole: "bank_code", hodnota: ucty[0].kod_banky, porovnat: bezMezer },
                            { pole: "bank_name", hodnota: ucty[0].nazev_banky }
                        );
                    }

                    var vysledek = roztridit(navrhy);

                    // Platce DPH: navrh jen na zaskrtnuti - nenalezeni v
                    // registru muze byt i vypadek sluzby, odskrtavat se
                    // podle toho nesmi. U noveho klienta je nezaskrtnuto
                    // jen vychozi stav, ne udaj - tam se zaskrtne rovnou.
                    var $platce = $("#id_vat_payer");
                    if ($platce.length && $platce.is(":visible") && !$platce.prop("checked") && (d.dic || reg.found)) {
                        if (currentClientId()) {
                            vysledek.zmeny.push({ pole: "vat_payer", ted: false, hodnota: true });
                        } else {
                            $platce.prop("checked", true).trigger("change");
                            vysledek.doplneno.push(POLE.vat_payer);
                        }
                    }

                    var hlaska = "✓ Načteno z ARES."
                        + (vysledek.doplneno.length ? " Doplněno: " + vysledek.doplneno.join(", ") + "." : "");
                    if (!vysledek.zmeny.length) {
                        hlaska += vysledek.doplneno.length ? "" : " Údaje odpovídají ARES.";
                    }
                    var varovani = reg && reg.nespolehlivy_platce === "ANO" ? " ⚠ NESPOLEHLIVÝ PLÁTCE DPH!" : "";
                    $status.text(
                        hlaska + (vysledek.zmeny.length ? " Liší se: " + vysledek.zmeny.length + " – viz níže." : "") + varovani
                    ).css("color", varovani ? "red" : (vysledek.zmeny.length ? "#d97706" : "green"));
                    zobrazitZmeny(vysledek.zmeny, $status, hlaska + varovani);
                });
            })
            .catch(function (err) {
                $status.text("✗ " + err.message).css("color", "red");
            });
    };
})();
