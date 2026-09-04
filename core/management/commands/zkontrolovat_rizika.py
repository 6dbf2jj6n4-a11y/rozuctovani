"""
Mesicni kontrola rizika: projde aktivni klienty s vyplnenym ICO a overi
v ARES dve veci, ktere signalizuji riziko dalsi spoluprace:

1. "v likvidaci" v nazvu firmy - pokud se objevi a nas ulozeny nazev to
   jeste neobsahuje, aktualizuje se nazev klienta na aktualni zneni z
   ARES - diky tomu se klient hned zvyrazni cervene v seznamu klientu
   v adminu (viz ClientAdmin.name_display).

2. Zaznam v insolvencnim rejstriku (ARES pole
   seznamRegistraci.stavZdrojeIr - viz core/ares_client.py) - ulozi se
   do Client.insolvency_status ("aktivni"/"historicky"/prazdne), coz se
   v adminu take barevne zvyrazni.

U klientu - fyzickych osob (OSVC, pravniForma "101") navic jen
informativne (nic se neuklada, neni to risk flag) vypise pocet
aktivnich provozoven ze zivnostenskeho rejstriku (RZP) - 0 aktivnich
muze byt uzitecny kontext k insolvenci/likvidaci, ale samo o sobe nic
neznamena (spousta OSVC podnika bez registrovane provozovny).

Samotna logika je v core/rizika.py - stejnou kontrolu spousti i tlacitko
"Zkontrolovat rizika (ARES)" nad seznamem Klientu v adminu.

Pouziti:
  python manage.py zkontrolovat_rizika
  python manage.py zkontrolovat_rizika --dry-run
"""
from django.core.management.base import BaseCommand

from core import rizika


class Command(BaseCommand):
    help = "Zkontroluje v ARES riziko u aktivních klientů: likvidace v názvu a záznam v insolvenčním rejstříku."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se změnilo")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        vysledek = rizika.zkontrolovat(dry_run=dry_run)

        nove_likvidace = vysledek["nove_likvidace"]
        nove_insolvence = vysledek["nove_insolvence"]

        if nove_likvidace:
            self.stdout.write(self.style.ERROR(f"\nNOVĚ zjištěno 'v likvidaci' u {len(nove_likvidace)} klientů:"))
            for _client, old_name, new_name in nove_likvidace:
                self.stdout.write(f"  {old_name} -> {new_name}")
        if vysledek["drive_likvidace"]:
            jmena = [c.name for c in vysledek["drive_likvidace"]]
            self.stdout.write(f"\nUž dříve označeno 'v likvidaci' ({len(jmena)}): " + ", ".join(jmena))

        if nove_insolvence:
            self.stdout.write(self.style.ERROR(f"\nNOVĚ zjištěno AKTIVNÍ insolvenční řízení u {len(nove_insolvence)} klientů:"))
            for client in nove_insolvence:
                self.stdout.write(f"  {client.name}")
        if vysledek["vyresene_insolvence"]:
            jmena = [c.name for c in vysledek["vyresene_insolvence"]]
            self.stdout.write(self.style.WARNING("\nInsolvenční řízení už není aktivní (bylo) u: " + ", ".join(jmena)))

        if vysledek["bez_provozovny"]:
            self.stdout.write(f"\nInformativně - OSVČ bez aktivní provozovny (RŽP, {len(vysledek['bez_provozovny'])}):")
            for client, zanikle in vysledek["bez_provozovny"]:
                self.stdout.write(f"  {client.name} (0 aktivních, {zanikle} zaniklých)")

        self.stdout.write(self.style.SUCCESS(
            f"\nHotovo{' (dry-run, nic se neulozilo)' if dry_run else ''}: zkontrolováno {vysledek['zkontrolovano']} "
            f"aktivních klientů s ICO, {len(vysledek['nenalezeno'])} nenalezeno v ARES, "
            f"{len(nove_likvidace)} nově 'v likvidaci', {len(nove_insolvence)} nově v aktivní insolvenci."
        ))
