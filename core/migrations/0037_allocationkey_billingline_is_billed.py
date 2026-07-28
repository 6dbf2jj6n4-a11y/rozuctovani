from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0036_backfill_landlord_representative"),
    ]

    operations = [
        migrations.AddField(
            model_name="allocationkey",
            name="is_billed",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Odpovida sloupci 'FinTok' v puvodnich Excel tabulkach klicu. Pokud NE: "
                    "castka se i tak zapocita do vypoctu (spravedlive snizuje podil ostatnich "
                    "karet na sdilenem nakladu), ale klientovi se samostatne NEFAKTURUJE - "
                    "typicky proto, ze uz ji ma zahrnutou v pausalni platbe (najem + energie "
                    "dohromady). Promita se do BillingLine.is_billed a do klientskeho PDF "
                    "vyuctovani (billing/statement_generator.py)."
                ),
                verbose_name="Fakturovat",
            ),
        ),
        migrations.AddField(
            model_name="billingline",
            name="is_billed",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Snimek AllocationKey.is_billed v okamziku vypoctu (viz billing/engine.py) - "
                    "castka se pocitala do rozpoctu vzdy, ale pokud NE, klientovi se v PDF "
                    "vyuctovani nepripocita do castky k uhrade (uz ji ma v pausalu)."
                ),
                verbose_name="Fakturováno klientovi",
            ),
        ),
    ]
