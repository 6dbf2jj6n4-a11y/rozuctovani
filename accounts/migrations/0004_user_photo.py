"""Fotka uzivatele - zobrazuje se v panelu dole v bocnim menu.

Na Danielovo prani 2026-08-18 ("chci pridat fotku misto postavicky pro
kazdeho uzivatele"). Panel uz avatar umel, ale jen jeden spolecny ze
statickeho souboru (core/img/avatar.jpg) - ten zustava jako zaloha.

Uklada se na R2 stejne jako fota odectu, protoze lokalni disk na Railway
je pomijivy (viz core/storage.py).
"""
import core.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_diacritika_popisku"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="photo",
            field=models.ImageField(
                blank=True, null=True,
                storage=core.storage.R2MediaStorage(),
                upload_to="uzivatele/",
                verbose_name="Fotka",
                help_text=(
                    "Zobrazí se v panelu přihlášeného uživatele dole v menu. "
                    "Ideálně čtvercová, stačí malá (např. 200×200). Bez fotky se "
                    "použije panáček."
                ),
            ),
        ),
    ]
