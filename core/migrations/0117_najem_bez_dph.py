from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0116_ztraty_do_jednotek"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientcard",
            name="najem_bez_dph",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Zapni, když jsou plátci obě strany, ale nájem se podle §56a "
                    "nechává osvobozený. Bez zaškrtnutí se u dvou plátců k nájemnému "
                    "DPH připočítává. U neplátce nebo bytu nemá vliv - tam se nájem "
                    "nedaní nikdy."
                ),
                verbose_name="Nájem bez DPH (osvobozeno)",
            ),
        ),
    ]
