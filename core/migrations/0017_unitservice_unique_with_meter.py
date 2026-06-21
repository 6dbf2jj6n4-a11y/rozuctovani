from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_unit_description_charfield"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="unitservice",
            unique_together={("unit", "service_item", "meter")},
        ),
    ]
