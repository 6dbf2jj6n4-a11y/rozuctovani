import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0026_allocationkey_deduct_from_pool"),
    ]

    operations = [
        migrations.AddField(
            model_name="allocationkey",
            name="unit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="allocation_keys",
                to="core.unit",
                verbose_name="Plocha",
                help_text=(
                    "Jen informativní - u pevné částky (fixed_amount) počítané z výměry "
                    "(K_PLOSE) označuje konkrétní plochu, ze které se paušál spočítal. "
                    "Pokud se pevná částka vztahuje na součet více ploch karty (napr. "
                    "srážkové vody), zůstává prázdné."
                ),
            ),
        ),
    ]
