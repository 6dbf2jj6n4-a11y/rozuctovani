/*
Pri vyberu plochy (Unit) v inline "Plochy a najemne" automaticky
vyplni pole "Vymera (m2) - uprava" hodnotou z zasobniku (Unit.area_m2),
pokud je pole prazdne (aby se neprepisovaly rucni upravy).
*/
document.addEventListener("change", function (e) {
    if (!e.target.matches('select[id$="-unit"]')) {
        return;
    }
    var row = e.target.closest("tr");
    if (!row) {
        return;
    }
    var areaInput = row.querySelector('input[id$="-area_m2_override"]');
    if (!areaInput || areaInput.value) {
        return;
    }
    var unitId = e.target.value;
    if (!unitId) {
        return;
    }
    fetch("/admin/core/unit/area-lookup/" + unitId + "/")
        .then(function (response) {
            return response.json();
        })
        .then(function (data) {
            if (data.area !== null && data.area !== undefined) {
                areaInput.value = data.area;
            }
        })
        .catch(function () {
            /* ticho - pokud lookup selze, pole jednoduse zustane prazdne */
        });
});
