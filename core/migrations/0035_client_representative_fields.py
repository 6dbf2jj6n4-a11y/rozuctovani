from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0034_site_lease_subject_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="representative_name",
            field=models.CharField(
                blank=True, max_length=200,
                help_text="Napr. 'Ing. Daniel DAVID' - u Pronajímatele se použije jako podpis ve Smlouvě.",
                verbose_name="Zástupce (jméno)",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="representative_role",
            field=models.CharField(
                blank=True, max_length=200,
                help_text="Napr. 'jediný člen představenstva' nebo 'jednatel'.",
                verbose_name="Zástupce (funkce)",
            ),
        ),
    ]
