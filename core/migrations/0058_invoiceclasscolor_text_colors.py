from django.db import migrations, models


def seed_text_colors(apps, schema_editor):
    InvoiceClassColor = apps.get_model("core", "InvoiceClassColor")
    # Konvence od Daniela (2026-08-16): elektrina zluta, teplo cervena,
    # voda modra, ostatni zelena. Dva odstiny stejne barvy - na bilem
    # pozadi je potreba tmavsi, na tmavem svetlejsi, jinak jeden z motivu
    # neni citelny. Najemne zustava neutralni (nepatri mezi energie).
    defaults = {
        "rent": ("#374151", "#d1d5db"),
        "electricity": ("#b45309", "#fbbf24"),
        "water": ("#2563eb", "#60a5fa"),
        "heat": ("#dc2626", "#f87171"),
        "other": ("#15803d", "#4ade80"),
    }
    for code, (light, dark) in defaults.items():
        InvoiceClassColor.objects.filter(invoice_class=code).update(
            text_color_light=light, text_color_dark=dark
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0057_period_is_current"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceclasscolor",
            name="text_color_light",
            field=models.CharField(
                default="#374151", max_length=7,
                help_text="Formát #rrggbb. Použije se v seznamech Měřidla, Odečty, Ceníky…",
                verbose_name="Barva textu (světlý motiv)",
            ),
        ),
        migrations.AddField(
            model_name="invoiceclasscolor",
            name="text_color_dark",
            field=models.CharField(
                default="#d1d5db", max_length=7,
                help_text="Formát #rrggbb.",
                verbose_name="Barva textu (tmavý motiv)",
            ),
        ),
        migrations.RunPython(seed_text_colors, migrations.RunPython.noop),
    ]
