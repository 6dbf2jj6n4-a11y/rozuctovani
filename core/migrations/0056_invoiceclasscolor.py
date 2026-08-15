from django.db import migrations, models


def seed_colors(apps, schema_editor):
    InvoiceClassColor = apps.get_model("core", "InvoiceClassColor")
    # Vychozi hodnoty odpovidaji tomu, co uz bylo napevno v kodu
    # (zluta/modra/cervena/neutralni) - Daniel si je pak muze v adminu
    # sam prebarvit.
    defaults = [
        ("rent", "#f3f4f6", "#1f2937"),
        ("electricity", "#fef9c3", "#422006"),
        ("water", "#dbeafe", "#1e3a5f"),
        ("heat", "#fee2e2", "#450a0a"),
        ("other", "#f3f4f6", "#1f2937"),
    ]
    for code, light, dark in defaults:
        InvoiceClassColor.objects.get_or_create(
            invoice_class=code, defaults={"color_light": light, "color_dark": dark}
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0055_meter_coefficient"),
    ]

    operations = [
        migrations.CreateModel(
            name="InvoiceClassColor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "invoice_class",
                    models.CharField(
                        choices=[
                            ("rent", "Nájemné"), ("electricity", "Elektřina"),
                            ("water", "Voda"), ("heat", "Teplo"), ("other", "Ostatní"),
                        ],
                        max_length=20, unique=True, verbose_name="Třída",
                    ),
                ),
                (
                    "color_light",
                    models.CharField(
                        default="#f3f4f6", help_text="Formát #rrggbb.", max_length=7,
                        verbose_name="Barva pozadí (světlý motiv)",
                    ),
                ),
                (
                    "color_dark",
                    models.CharField(
                        default="#1f2937", help_text="Formát #rrggbb.", max_length=7,
                        verbose_name="Barva pozadí (tmavý motiv)",
                    ),
                ),
            ],
            options={
                "verbose_name": "Barva třídy",
                "verbose_name_plural": "Barvy tříd",
                "ordering": ["invoice_class"],
            },
        ),
        migrations.RunPython(seed_colors, migrations.RunPython.noop),
    ]
