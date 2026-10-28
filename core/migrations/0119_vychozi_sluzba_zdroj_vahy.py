# Vychozi sluzba plochy pamatuje, odkud brat vahu, a predava to Klicum.
# Daniel 2026-10-28.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0118_karta_bez_priznaku_aktivni"),
    ]

    operations = [
        migrations.AddField(
            model_name="unitservice",
            name="weight_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Hodnota zadaná ručně"),
                    ("plocha", "Celá plocha karty (m²)"),
                    ("vytapena", "Vytápěná plocha karty (m²)"),
                    ("osoby", "Počet osob z karty"),
                    ("osoby_tuv", "Počet osob pro TUV z karty"),
                ],
                default="",
                help_text=(
                    "Váha se spočítá z Karty, na kterou plocha přijde – nemusíš znát "
                    "výměru ani počet osob. Když necháš „Hodnota zadaná ručně“ "
                    "a Hodnotu prázdnou, doplní se to, co u téhle položky a měřidla "
                    "používají ostatní Karty areálu."
                ),
                max_length=20,
                verbose_name="Odkud brát váhu",
            ),
        ),
    ]
