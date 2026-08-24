"""PSČ jednotně ve tvaru "620 00".

V databázi byly oba zápisy vedle sebe: ručně zadaná PSČ s mezerou,
ta natažená z ARES bez ní (core.ares_client vrací holých pět číslic).
Od teď to sjednocuje Client.save přes core.models.normalizovat_psc,
tahle migrace srovná, co už v databázi je.

Pole samotné se nemění, jde čistě o data - proto žádné AlterField.
Daniel 2026-08-25.
"""
from django.db import migrations


def sjednotit(apps, schema_editor):
    # Cista funkce nad retezcem, nezavisi na stavu modelu - historicky
    # model (apps.get_model) tu proto nevadi. Stejny postup jako
    # v migracich 0075, 0083, 0084 a 0085.
    from core.models import normalizovat_psc

    Client = apps.get_model("core", "Client")
    for klient in Client.objects.exclude(zip_code=""):
        novy = normalizovat_psc(klient.zip_code)
        if novy != klient.zip_code:
            Client.objects.filter(pk=klient.pk).update(zip_code=novy)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0085_dic_bez_mezer"),
    ]

    operations = [
        # Zpetny chod zamerne nic nedela - slo jen o zapis tehoz PSC.
        migrations.RunPython(sjednotit, migrations.RunPython.noop),
    ]
