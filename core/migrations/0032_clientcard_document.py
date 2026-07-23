from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0031_inflationrate"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientcard",
            name="document",
            field=models.FileField(
                blank=True, null=True, upload_to="karty/",
                verbose_name="Vygenerovaný dokument (Karta nájemce)",
            ),
        ),
    ]
