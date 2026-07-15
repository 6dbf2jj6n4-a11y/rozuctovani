from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("core", "0019_billingline_units"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="sites",
            field=models.ManyToManyField(
                blank=True,
                related_name="managers",
                to="core.site",
                verbose_name="Areály",
                help_text="Areály ke kterým má správce přístup. Prázdné = přístup ke všem (admin).",
            ),
        ),
    ]
