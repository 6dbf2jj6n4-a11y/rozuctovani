from django.db import migrations, models


def seed_meter_types(apps, schema_editor):
    MeterTypeConfig = apps.get_model("core", "MeterTypeConfig")
    # Vychozi hodnoty odpovidaji tomu, co uz bylo napevno v kodu
    # (Meter.MeterType enum + METER_TYPE_TO_CLASS + unit-of-measure
    # fallback slovnik v core/admin.py) - Daniel si je pak muze v adminu
    # sam upravit/pridat/smazat.
    defaults = [
        ("electricity", "Elektřina", "kWh", "electricity", 0),
        ("water", "Voda", "m³", "water", 1),
        ("gas", "Plyn", "m³", "other", 2),
        ("heat", "Teplo", "GJ", "heat", 3),
        ("other", "Jiné", "", "other", 4),
    ]
    for code, label, unit, invoice_class, sort_order in defaults:
        MeterTypeConfig.objects.get_or_create(
            code=code,
            defaults={
                "label": label,
                "default_unit_of_measure": unit,
                "invoice_class": invoice_class,
                "sort_order": sort_order,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0061_invoiceclass_deduct_fixed"),
    ]

    operations = [
        migrations.CreateModel(
            name="MeterTypeConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "code",
                    models.CharField(
                        help_text="Interní kód (např. 'electricity') - používá se v datech měřidel. Needitovatelné po založení.",
                        max_length=20, unique=True, verbose_name="Kód",
                    ),
                ),
                ("label", models.CharField(max_length=50, verbose_name="Název")),
                (
                    "default_unit_of_measure",
                    models.CharField(
                        blank=True,
                        help_text="Návrh jednotky pro měřidla tohoto typu, která nemají vlastní jednotku vyplněnou.",
                        max_length=20, verbose_name="Výchozí měrná jednotka",
                    ),
                ),
                (
                    "invoice_class",
                    models.CharField(
                        blank=True,
                        help_text="Do které Třídy (Nastavení -> Třídy - barvy, paušály) se měřidla tohoto typu počítají. Prázdné = nepočítá se do žádné.",
                        max_length=20, verbose_name="Třída fakturace",
                    ),
                ),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Pořadí")),
            ],
            options={
                "verbose_name": "Typ měřidla",
                "verbose_name_plural": "Typy měřidel",
                "ordering": ["sort_order", "code"],
            },
        ),
        migrations.AlterField(
            model_name="meter",
            name="meter_type",
            field=models.CharField(max_length=20, verbose_name="Typ"),
        ),
        migrations.AlterField(
            model_name="supplypoint",
            name="meter_type",
            field=models.CharField(default="electricity", max_length=20, verbose_name="Typ energie"),
        ),
        migrations.RunPython(seed_meter_types, migrations.RunPython.noop),
    ]
