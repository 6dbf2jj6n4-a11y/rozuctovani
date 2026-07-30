from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_user_sites'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='user',
            options={'verbose_name': 'Uživatel', 'verbose_name_plural': 'Uživatelé'},
        ),
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(choices=[('admin', 'Administrátor'), ('spravce', 'Správce'), ('klient', 'Klient')], default='klient', max_length=20, verbose_name='Role'),
        ),
    ]
