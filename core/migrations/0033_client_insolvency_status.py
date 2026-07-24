from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0032_clientcard_document"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="insolvency_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "—"),
                    ("aktivni", "Aktivní insolvenční řízení"),
                    ("historicky", "Dřívější insolvenční řízení (uzavřeno)"),
                ],
                help_text=(
                    "Vyplňuje se automaticky měsíční kontrolou proti ARES "
                    "(core/management/commands/zkontrolovat_rizika.py) - neupravuj ručně."
                ),
                max_length=20,
                verbose_name="Insolvenční rejstřík",
            ),
        ),
    ]
