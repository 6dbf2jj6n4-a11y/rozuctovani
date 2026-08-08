from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0049_remove_meterreading_is_estimate"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientcard",
            name="signed_on",
            field=models.DateField(
                blank=True,
                help_text="Tiskne se na Kartu nájemce (Příloha č. 1). Pokud není vyplněno, předvyplní se při uložení podle Platnost od.",
                null=True,
                verbose_name="Datum podpisu",
            ),
        ),
    ]
