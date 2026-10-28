# O platnosti Karty rozhoduji jen data Platnost od/do - priznak Aktivni
# se rozchazel s daty a prevod z planku kvuli nemu zakladal nove Karty.
# Daniel 2026-10-28.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0117_najem_bez_dph"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="clientcard",
            name="is_active",
        ),
    ]
