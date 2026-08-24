"""Klient bez telefonu ma mit pole PRAZDNE.

Pole Client.contact_phone melo default="+420 ", takze nove zalozenemu
klientovi v nem visela osamocena predvolba. Predvolbu nabizi az combo ve
formulari (core.admin.TelefonWidget); do databaze patri jen skutecne
cislo. Daniel 2026-08-24.

Migrace zaroven procisti, co uz v databazi je - normalizovat_telefon
dneska vraci prazdno pro samotnou predvolbu a cisla bez rozpoznatelne
predvolby deli do trojic (format je vzdycky XXX XXX XXX).

Psano rucne, ne pres makemigrations: to na tomhle repu navrhuje i
nesouvisejici zmeny z historickeho driftu mezi modely a migracemi.
"""
from django.db import migrations, models


def procistit(apps, schema_editor):
    # Cista funkce nad retezcem, nezavisi na stavu modelu - historicky
    # model (apps.get_model) tu proto nevadi. Stejny postup jako
    # v migraci 0075.
    from core.models import normalizovat_telefon

    Client = apps.get_model("core", "Client")
    for klient in Client.objects.exclude(contact_phone=""):
        novy = normalizovat_telefon(klient.contact_phone)
        if novy != klient.contact_phone:
            Client.objects.filter(pk=klient.pk).update(contact_phone=novy)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0082_site_landlord"),
    ]

    operations = [
        migrations.AlterField(
            model_name="client",
            name="contact_phone",
            field=models.CharField(
                blank=True,
                help_text="Číslo stačí napsat bez mezer, uloží se ve tvaru +420 123 456 789.",
                max_length=50, verbose_name="Telefon",
            ),
        ),
        # Zpetny chod zamerne nic nedela: vratit "+420 " do prazdnych
        # poli nema smysl a puvodni tvary uz nejsou z ceho obnovit.
        migrations.RunPython(procistit, migrations.RunPython.noop),
    ]
