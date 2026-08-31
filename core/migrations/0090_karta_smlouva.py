"""Vazba Karty na Smlouvu.

Karty a smlouvy spolu dosud nijak nesouvisely - ze smlouvy se dalo poznat
jen to, ze patri stejnemu klientovi. Pritom koncept je takovy, ze
**smlouva se behem najmu nemeni**, kdezto Karet ma klient v case vic:
Kartou se meni predmet najmu (pribude plocha, zmeni se najemne), aniz by
se sepisoval dodatek. Smlouva tak ma vic priloh - Karet.

Pole je nepovinne: Karty z puvodniho importu smlouvu prirazenou nemaji
a nektere ke smlouve ani nepatri.

Viz Daniel 2026-09-08.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0089_predmet_najmu"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientcard",
            name="contract",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cards",
                to="core.contract",
                verbose_name="Smlouva",
                help_text=(
                    "Smlouva, ke které je tahle Karta přílohou. Smlouva se během "
                    "nájmu nemění, kdežto Karet může mít klient v čase víc - mění "
                    "se jimi předmět nájmu, aniž by se sepisoval nový dodatek. "
                    "Nechej prázdné u Karet, které ke smlouvě nepatří."
                ),
            ),
        ),
    ]
