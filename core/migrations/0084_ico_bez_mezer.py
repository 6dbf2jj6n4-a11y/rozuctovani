"""IČO se zobrazuje i ukládá bez mezer.

Část IČO přišla rozdělená po trojicích ("285 64 961"). Kromě vzhledu
v seznamu klientů to vadilo i věcně: takové IČO nešlo poslat do ARES
a neshodlo se při kontrole duplicity (core.admin.ico_lookup hledá na
přesnou shodu). Od teď to sjednocuje Client.save přes
core.models.normalizovat_ico, tahle migrace srovná, co už v databázi je.

Pole samotné se nemění, jde čistě o data - proto žádné AlterField.
Daniel 2026-08-24.
"""
from django.db import migrations


def bez_mezer(apps, schema_editor):
    # Cista funkce nad retezcem, nezavisi na stavu modelu - historicky
    # model (apps.get_model) tu proto nevadi. Stejny postup jako
    # v migracich 0075 a 0083.
    from core.models import normalizovat_ico

    Client = apps.get_model("core", "Client")
    for klient in Client.objects.exclude(ico=""):
        novy = normalizovat_ico(klient.ico)
        if novy != klient.ico:
            Client.objects.filter(pk=klient.pk).update(ico=novy)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0083_telefon_bez_vychozi_predvolby"),
    ]

    operations = [
        # Zpetny chod zamerne nic nedela - kam presne mezery patrily uz
        # neni z ceho obnovit a slo jen o zapis tehoz cisla.
        migrations.RunPython(bez_mezer, migrations.RunPython.noop),
    ]
