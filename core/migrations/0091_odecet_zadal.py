"""Kdo odecet zapsal.

U odectu nebylo poznat, kdo hodnotu odecetl a zadal - pri nesrovnalosti
se nemel kdo doptat. Pole se vyplni samo pri zapisu ze Zadavani odectu
i z administrace; u odectu z importu a u starsich zaznamu zustava
prazdne.

Viz Daniel 2026-09-01.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0090_karta_smlouva"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="meterreading",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="zapsane_odecty",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Zadal",
                help_text=(
                    "Kdo stav odečetl a zapsal. Vyplní se samo při zápisu z "
                    "Odečtů i z administrace; u odečtů z importu a u starších "
                    "záznamů zůstává prázdné."
                ),
            ),
        ),
    ]
