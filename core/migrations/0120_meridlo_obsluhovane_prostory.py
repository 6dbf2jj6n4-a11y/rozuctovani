# Meridlo vi, ktere Prostory meri - vaha z plochy na meridle pak bere jen
# plochy Karty pod nim. Daniel 2026-10-28.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0119_vychozi_sluzba_zdroj_vahy"),
    ]

    operations = [
        migrations.AddField(
            model_name="meter",
            name="plochy",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "Prostory, jejichž spotřebu tohle měřidlo měří (např. E_AB2 = kanceláře "
                    "ve 2.NP). Klíče s váhou „Celá plocha“ nebo „Vytápěná plocha“ na tomhle "
                    "měřidle pak počítají jen plochy Karty, které sem patří. Nech prázdné, "
                    "když měřidlo dělí podle celé plochy Karty (E_SPOL, teplo NJ)."
                ),
                related_name="meridla",
                to="core.unit",
                verbose_name="Obsluhované prostory",
            ),
        ),
    ]
