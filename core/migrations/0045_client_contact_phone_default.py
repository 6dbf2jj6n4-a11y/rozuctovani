from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0044_client_entity_type_registry_source"),
    ]

    operations = [
        migrations.AlterField(
            model_name="client",
            name="contact_phone",
            field=models.CharField(
                blank=True,
                default="+420 ",
                help_text="Formát: +420 777123456.",
                max_length=50,
                verbose_name="Telefon",
            ),
        ),
    ]
