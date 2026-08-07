from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0047_clientcard_po_number"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="client",
            name="note",
        ),
    ]
