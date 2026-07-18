import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0027_allocationkey_unit"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="registry_court",
            field=models.CharField(
                blank=True,
                max_length=100,
                verbose_name="Rejstříkový soud",
                help_text=(
                    "Napr. 'Krajský soud v Ostravě' - lze dohledat/overit pres ARES podle IČO."
                ),
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="registry_section",
            field=models.CharField(blank=True, max_length=20, verbose_name="Oddíl"),
        ),
        migrations.AddField(
            model_name="client",
            name="registry_insert",
            field=models.CharField(blank=True, max_length=20, verbose_name="Vložka"),
        ),
        migrations.CreateModel(
            name="Contract",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(blank=True, max_length=50, verbose_name="Číslo smlouvy")),
                ("signed_on", models.DateField(blank=True, null=True, verbose_name="Datum podpisu")),
                ("valid_from", models.DateField(blank=True, null=True, verbose_name="Platnost od")),
                (
                    "valid_to",
                    models.DateField(
                        blank=True, null=True, verbose_name="Platnost do",
                        help_text="Prázdné = na dobu neurčitou.",
                    ),
                ),
                (
                    "notice_period_months",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="Výpovědní lhůta (měsíce)"
                    ),
                ),
                (
                    "deposit_czk",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True,
                        verbose_name="Kauce (Kč)",
                    ),
                ),
                ("deposit_paid", models.BooleanField(default=False, verbose_name="Kauce zaplacena")),
                (
                    "insurance_amount_czk",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True,
                        verbose_name="Částka pojištění (Kč)",
                    ),
                ),
                (
                    "has_inflation_clause",
                    models.BooleanField(default=False, verbose_name="Inflační doložka"),
                ),
                (
                    "inflation_increase_from",
                    models.DateField(
                        blank=True, null=True, verbose_name="Inflační navýšení platí od",
                        help_text="Jen pokud je zaškrtnutá inflační doložka.",
                    ),
                ),
                (
                    "invoicing_email",
                    models.EmailField(
                        blank=True, max_length=254, verbose_name="E-mail pro elektronickou fakturaci",
                        help_text="Pokud se liší od kontaktního e-mailu klienta.",
                    ),
                ),
                (
                    "representative_name",
                    models.CharField(blank=True, max_length=200, verbose_name="Zastupuje (jméno)"),
                ),
                (
                    "representative_role",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="Zastupuje (funkce)",
                        help_text="Napr. 'jednatel', 'na základě plné moci'.",
                    ),
                ),
                (
                    "document",
                    models.FileField(
                        blank=True, null=True, upload_to="smlouvy/", verbose_name="Vygenerovaný dokument"
                    ),
                ),
                ("note", models.TextField(blank=True, verbose_name="Poznámka")),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contracts",
                        to="core.client",
                        verbose_name="Klient",
                    ),
                ),
            ],
            options={
                "verbose_name": "Smlouva",
                "verbose_name_plural": "Smlouvy",
                "ordering": ["-valid_from"],
            },
        ),
    ]
