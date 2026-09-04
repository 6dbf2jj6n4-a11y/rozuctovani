"""Naklad na Odbernem miste slouzi i k porovnani s privodnim meridlem.

Pole se dosud jmenovalo "Naklad, ze ktereho brat fakturovane mnozstvi"
a delalo jedinou vec: prepisovalo fakturovane mnozstvi do privodniho
meridla. To vychazelo z predpokladu, ze hlavni meridlo nikdo fyzicky
nectе a slouzi jen jako schranka na cislo z faktury. U vody v NJ ten
predpoklad padl, jakmile ji zacal spravce odecitat - odecet a faktura
si zacaly prepisovat jedno a totez pole a nedaly se porovnat.

Nove ma pole dve role: v Prehledu spotreb se fakturovane mnozstvi
porovna s tim, co namerilo privodni meridlo, a naplni se jim meridlo
jen tam, kde se rucne neodecita (rezim "spotreba").

Viz Daniel 2026-09-04.
"""
from django.db import migrations, models
import django.db.models.deletion

NAPOVEDA = (
    "Položka zásobníku, na které se za tenhle odběr účtuje. Použije "
    "se dvakrát: v Přehledu spotřeb se její Fakturované množství "
    "porovná s tím, co naměřilo Přívodní měřidlo, a u odběrů BEZ "
    "vlastního odečtu (přívodní měřidlo v režimu „spotřeba“) se jím "
    "měřidlo rovnou naplní akcí „Dotáhnout fakturovaná množství“ "
    "u Období. Do měřidla, které se odečítá ručně (režim „stav“), "
    "se nikdy nezapisuje - přepsalo by správcův odečet. "
    "Hádat položku podle areálu a třídy nejde: teplo NJ má dvě "
    "(pelety a záložní elektrokotel) a u vody by se do toho "
    "připletly srážkové vody, které v jednotkách nesou m² plochy, "
    "ne m³."
)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0094_popisky_po_slouceni_typu"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supplypoint",
            name="cost_item",
            field=models.ForeignKey(
                blank=True, help_text=NAPOVEDA, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="supplies_as_cost_source", to="core.servicepoolitem",
                verbose_name="Náklad (faktura) tohoto odběru",
            ),
        ),
    ]
