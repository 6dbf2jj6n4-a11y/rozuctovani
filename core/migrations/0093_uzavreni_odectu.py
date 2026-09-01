"""Uzavření odečtů za období a areál.

Správce tím řekne "mám hotovo" - odečty v tom areálu už na obrazovce
zadávání nejdou měnit a admin ví, že se na ně může spolehnout. Není to
totéž co uzavření Období (Period.status), které zamyká i náklady
a vyúčtování a dělá ho admin.

Granularita areál + období, protože odečty chodí po areálech: FM může
být hotové, když se v NJ ještě obchází. Daniel 2026-09-01.

Psáno ručně, ne přes makemigrations - to na tomhle repu navrhuje i
nesouvisející změny z historického driftu mezi modely a migracemi.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0092_jeden_typ_podle_vahy"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReadingsClosure",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("closed_at", models.DateTimeField(auto_now_add=True, verbose_name="Uzavřeno")),
                ("note", models.CharField(blank=True, max_length=300, verbose_name="Poznámka")),
                ("closed_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="readings_closures", to="accounts.user",
                    verbose_name="Uzavřel")),
                ("period", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="readings_closures", to="core.period",
                    verbose_name="Období")),
                ("site", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="readings_closures", to="core.site",
                    verbose_name="Areál")),
            ],
            options={
                "verbose_name": "Uzavření odečtů",
                "verbose_name_plural": "Uzavření odečtů",
                "ordering": ["-period__year", "-period__month", "site__name"],
            },
        ),
        migrations.AddConstraint(
            model_name="readingsclosure",
            constraint=models.UniqueConstraint(
                fields=("period", "site"),
                name="jedno_uzavreni_odectu_na_areal_a_obdobi"),
        ),
    ]
