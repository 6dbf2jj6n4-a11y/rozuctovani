"""Smlouvy a Karty najemce se ukladaji na Cloudflare R2 misto disku
kontejneru - ten se pri kazdem nasazeni na Railway vymaze, takze
vygenerovane i rucne nahrane dokumenty mizely (Daniel 2026-10-01).
V DB je jen cesta, data se nemeni."""
import core.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0114_rezim_vytapena_plocha"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contract",
            name="document",
            field=models.FileField(
                blank=True, null=True, storage=core.storage.R2MediaStorage(),
                upload_to="smlouvy/", verbose_name="Dokument smlouvy",
            ),
        ),
        migrations.AlterField(
            model_name="clientcard",
            name="document",
            field=models.FileField(
                blank=True, null=True, storage=core.storage.R2MediaStorage(),
                upload_to="karty/", verbose_name="Vygenerovaný dokument (Karta nájemce)",
            ),
        ),
    ]
