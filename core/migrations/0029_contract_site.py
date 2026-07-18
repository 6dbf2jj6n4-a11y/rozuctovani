import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0028_contract"),
    ]

    operations = [
        migrations.AddField(
            model_name="contract",
            name="site",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="contracts",
                to="core.site",
                verbose_name="Areál",
                help_text="Potřeba pro záhlaví generovaného dokumentu smlouvy.",
            ),
        ),
    ]
