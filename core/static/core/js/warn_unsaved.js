/*
Varování při odchodu z rozeditovaného formuláře (Karta klienta).

Náhrada za Unfoldí warn_unsaved_form, které na této stránce rozbíjelo
tlačítko "Přidat" u inline klíčů. Tenhle skript jen sleduje změny polí a
při odchodu z neuložené stránky (např. kliknutí na šipky Předchozí/Další,
což jsou obyčejné <a href> odkazy) vyvolá nativní potvrzení prohlížeče.

Přidání inline řádku ani uložení formuláře nikam nenaviguje / rovnou
odesílá, takže se varování v těch případech neuplatní a "Přidat" funguje
normálně. Viz konverzace s Danielem.
*/
(function () {
    var form = document.querySelector("#content-main form");
    if (!form) {
        return;
    }
    var dirty = false;
    function markDirty() {
        dirty = true;
    }
    // capture=true: chytí i změny ze select2/Unfold widgetů
    form.addEventListener("change", markDirty, true);
    form.addEventListener("input", markDirty, true);
    // Odeslání formuláře (Uložit) = záměrný odchod, nevaruj
    form.addEventListener("submit", function () {
        dirty = false;
    });
    window.addEventListener("beforeunload", function (e) {
        if (dirty) {
            e.preventDefault();
            e.returnValue = "";
        }
    });
})();
