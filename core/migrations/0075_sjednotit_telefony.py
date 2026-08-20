"""Sjednoceni zapisu telefonu klientu na "+420 777 913 623".

Na Danielovo prani 2026-08-19 - do pole se da napsat treba 777913623 a
ulozi se uz v jednotnem tvaru (Client.save volá normalizovat_telefon).
Tahle migrace srovna i cisla, ktera uz v databazi jsou, aby seznam
klientu vypadal jednotne.

Prepisuji se JEN cisla, ktera jdou spolehlive rozpoznat (ceska/slovenska
predvolba nebo 9 cislic bez ni). Cokoliv jineho - klapky, vic cisel v
jednom poli, jine zeme - zustava presne tak, jak to nekdo zapsal.
"""
from django.db import migrations, models


def sjednotit(apps, schema_editor):
    # Funkce se importuje z modelu zamerne: je to cistá funkce nad
    # retezcem, nezavisi na stavu modelu, takze historicky model
    # (apps.get_model) tu nevadi.
    from core.models import normalizovat_telefon

    Client = apps.get_model("core", "Client")
    for klient in Client.objects.exclude(contact_phone=""):
        novy = normalizovat_telefon(klient.contact_phone)
        if novy != klient.contact_phone:
            Client.objects.filter(pk=klient.pk).update(contact_phone=novy)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0074_areal_do_koeficientu_dph"),
    ]

    operations = [
        migrations.AlterField(
            model_name="client",
            name="contact_phone",
            field=models.CharField(
                blank=True, default="+420 ",
                help_text="Stačí napsat 777913623, uloží se jako +420 777 913 623.",
                max_length=50, verbose_name="Telefon",
            ),
        ),
        # Zpetny chod zamerne nic nedela - puvodni (ruzne) tvary uz nejsou
        # z ceho obnovit a slo jen o formatovani.
        migrations.RunPython(sjednotit, migrations.RunPython.noop),
    ]
