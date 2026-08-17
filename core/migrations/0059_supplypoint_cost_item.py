import django.db.models.deletion
from django.db import migrations, models


def predvyplnit(apps, schema_editor):
    """Kde to jde jednoznacne urcit, nastavi cost_item rovnou - tj. u
    odberu, jejichz privodni meridlo je nevirtualni a v rezimu "Spotreba
    za obdobi" (do takoveho se pise fakturovane mnozstvi) a v arealu
    existuje pro danou tridu PRAVE JEDNA polozka "hlavní odběr ...".
    Nejednoznacne pripady (teplo NJ ma pelety i zalozni elektrokotel)
    zustanou prazdne a Daniel je doplni v adminu."""
    SupplyPoint = apps.get_model("core", "SupplyPoint")
    ServicePoolItem = apps.get_model("core", "ServicePoolItem")

    meter_type_to_class = {
        "electricity": "electricity", "water": "water",
        "heat": "heat", "gas": "other", "other": "other",
    }
    for sp in SupplyPoint.objects.select_related("main_meter"):
        m = sp.main_meter
        if m is None or m.is_virtual or m.reading_mode != "consumption":
            continue
        vsechny = list(ServicePoolItem.objects.filter(
            site_id=sp.site_id,
            invoice_class=meter_type_to_class.get(sp.meter_type, "other"),
        ))
        # Jen kdyz je pro tu tridu v arealu polozka JEDINA. Nestaci hledat
        # "hlavní odběr" a spolehnout se, ze bude jen jedna: teplo NJ ma
        # "hlavní odběr teplo NJ" (zalozni elektrokotel) I "teplo - spotřeba
        # pelet NJ", a privod PELETY NJ patri k peletam - podle nazvu by
        # vysel elektrokotel. Radeji nechat prazdne a doplnit v adminu.
        if len(vsechny) == 1:
            sp.cost_item = vsechny[0]
            sp.save(update_fields=["cost_item"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0058_invoiceclasscolor_text_colors"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplypoint",
            name="cost_item",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="supplies_as_cost_source",
                to="core.servicepoolitem",
                verbose_name="Náklad, ze kterého brát fakturované množství",
                help_text=(
                    "Položka zásobníku, jejíž Fakturované množství se má přepisovat "
                    "do Přívodního měřidla (akce „Dotáhnout fakturovaná množství“ "
                    "u Období). Nastav jen u odběrů, kde se dodané množství bere "
                    "z faktury, ne z vlastního měřidla - jinak nech prázdné. "
                    "Hádat to podle areálu a třídy nejde: teplo NJ má dvě položky "
                    "(pelety a záložní elektrokotel) a u vody by se do toho připletly "
                    "srážkové vody, které v jednotkách nesou m² plochy, ne m³."
                ),
            ),
        ),
        migrations.RunPython(predvyplnit, migrations.RunPython.noop),
    ]
