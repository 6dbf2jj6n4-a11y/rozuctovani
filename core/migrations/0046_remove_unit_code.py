from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0045_client_contact_phone_default"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="unit",
            name="code",
        ),
    ]
