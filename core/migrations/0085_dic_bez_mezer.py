"""DIČ bez mezer, stejně jako IČO.

Migrace 0084 srovnala IČO. Pravidlo tehdy mezery odstraňovalo jen
u hodnot složených POUZE z číslic, aby nepřepisovalo zahraniční
registrační čísla - jenže DIČ má vždycky předponu země ("CZ28564961"),
takže by se ho takové pravidlo vůbec netýkalo. Mezera uvnitř
registračního čísla je vždycky jen způsob zápisu, nikdy součást
hodnoty, proto normalizovat_identifikator odstraňuje mezery vždy.

Tahle migrace projde znovu i IČO - kvůli tomu širšímu pravidlu.
Daniel 2026-08-24.
"""
from django.db import migrations


def bez_mezer(apps, schema_editor):
    # Cista funkce nad retezcem, nezavisi na stavu modelu - historicky
    # model (apps.get_model) tu proto nevadi. Stejny postup jako
    # v migracich 0075, 0083 a 0084.
    from core.models import normalizovat_identifikator

    Client = apps.get_model("core", "Client")
    for klient in Client.objects.exclude(ico="", dic=""):
        novy_ico = normalizovat_identifikator(klient.ico)
        novy_dic = normalizovat_identifikator(klient.dic)
        if (novy_ico, novy_dic) != (klient.ico, klient.dic):
            Client.objects.filter(pk=klient.pk).update(ico=novy_ico, dic=novy_dic)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0084_ico_bez_mezer"),
    ]

    operations = [
        # Zpetny chod zamerne nic nedela - kam presne mezery patrily uz
        # neni z ceho obnovit a slo jen o zapis tehoz cisla.
        migrations.RunPython(bez_mezer, migrations.RunPython.noop),
    ]
