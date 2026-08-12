import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0050_clientcard_signed_on"),
    ]

    operations = [
        migrations.CreateModel(
            name="SupplyPoint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Např. 'EAN 668' nebo 'Hlavní odběr elektro FM'.", max_length=200, verbose_name="Název")),
                ("code", models.CharField(blank=True, max_length=50, verbose_name="Kód / EAN")),
                (
                    "meter_type",
                    models.CharField(
                        choices=[
                            ("electricity", "Elektřina"),
                            ("water", "Voda"),
                            ("gas", "Plyn"),
                            ("heat", "Teplo"),
                            ("other", "Jiné"),
                        ],
                        default="electricity",
                        max_length=20,
                        verbose_name="Typ energie",
                    ),
                ),
                ("note", models.CharField(blank=True, max_length=300, verbose_name="Poznámka")),
                (
                    "main_meter",
                    models.ForeignKey(
                        blank=True,
                        help_text=(
                            "Měřidlo, jehož spotřeba = kolik do odběrného místa celkem došlo od dodavatele "
                            "(např. 668_CELKEM). Nech prázdné, pokud se dodané množství bere jen z faktury a "
                            "žádné hlavní měřidlo neexistuje."
                        ),
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="supplies_as_main",
                        to="core.meter",
                        verbose_name="Přívodní měřidlo (dodaná spotřeba)",
                    ),
                ),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="supply_points",
                        to="core.site",
                        verbose_name="Areál",
                    ),
                ),
            ],
            options={
                "verbose_name": "Odběrné místo",
                "verbose_name_plural": "Odběrná místa",
                "ordering": ["site", "meter_type", "name"],
            },
        ),
        migrations.AddField(
            model_name="meter",
            name="supply_point",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Pod které odběrné místo (EAN) toto měřidlo fyzicky patří. Slouží k reconciliaci "
                    "'dodáno vs. naměřeno' v přehledu spotřeb. Nech prázdné u přívodního/fakturačního "
                    "měřidla samotného odběru (např. 668_CELKEM) - to se nastavuje na Odběrném místě "
                    "jako 'Přívodní měřidlo', ne jako jeho vlastní člen."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="member_meters",
                to="core.supplypoint",
                verbose_name="Odběrné místo",
            ),
        ),
    ]
