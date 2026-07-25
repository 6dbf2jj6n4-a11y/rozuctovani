from django.db import migrations


def backfill_landlord_representative(apps, schema_editor):
    """Docasny most pro prechod z pevnych LANDLORD_NAME/LANDLORD_REPRESENTATIVE
    konstant (core/contract_generator.py) na dynamicke udaje z Client.is_landlord.

    Pokud je v databazi prave jeden Klient oznaceny jako Pronajimatel, doplni mu
    Zastupce (jmeno/funkce), a to jen tam, kde je pole prazdne - takze se text
    generovane Smlouvy pro nej nezmeni oproti puvodnimu hardcodovanemu stavu.
    Pokud takovy Klient neexistuje (nebo jich je vic), nedela nic - je potreba
    dorešit rucne v adminu pred prvnim generovanim Smlouvy."""
    Client = apps.get_model("core", "Client")
    landlords = list(Client.objects.filter(is_landlord=True))
    if len(landlords) != 1:
        return
    landlord = landlords[0]
    changed = False
    if not landlord.representative_name:
        landlord.representative_name = "Ing. Daniel DAVID"
        changed = True
    if not landlord.representative_role:
        landlord.representative_role = "jediný člen představenstva"
        changed = True
    if changed:
        landlord.save(update_fields=["representative_name", "representative_role"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0035_client_representative_fields"),
    ]

    operations = [
        migrations.RunPython(backfill_landlord_representative, noop),
    ]
