from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0043_odecty_foto_vymena_poradi"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="entity_type",
            field=models.CharField(
                blank=True,
                choices=[("pravnicka", "Právnická osoba"), ("fyzicka", "Fyzická osoba")],
                max_length=20,
                verbose_name="Typ osoby",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="registry_source",
            field=models.CharField(
                blank=True,
                choices=[("obchodni", "Obchodní rejstřík"), ("zivnostensky", "Živnostenský rejstřík")],
                help_text="Ze kterého rejstříku pochází identifikační údaje klienta (IČO, sídlo...).",
                max_length=20,
                verbose_name="Zdroj údajů",
            ),
        ),
    ]
