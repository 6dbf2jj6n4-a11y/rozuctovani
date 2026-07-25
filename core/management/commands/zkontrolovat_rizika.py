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

Pouziti:
  python manage.py zkontrolovat_rizika
  python manage.py zkontrolovat_rizika --dry-run
"""
import time

from django.core.management.base import BaseCommand

from core.ares_client import PRAVNI_FORMA_OSVC, lookup_company, lookup_trade_register
from core.models import Client


class Command(BaseCommand):
    help = "Zkontroluje v ARES riziko u aktivních klientů: likvidace v názvu a záznam v insolvenčním rejstříku."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se změnilo")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        clients = Client.objects.filter(is_active=True).exclude(ico="").order_by("name")

        newly_liquidation = []
        already_liquidation = []
        newly_insolvent = []
        resolved_insolvent = []
        no_active_provozovna = []
        not_found = 0

        for client in clients:
            company = lookup_company(client.ico)
            if not company or not company.get("name"):
                not_found += 1
                time.sleep(0.2)
                continue

            # 1) likvidace v nazvu
            ares_name = company["name"]
            if "v likvidaci" in ares_name.lower():
                if "v likvidaci" in client.name.lower():
                    already_liquidation.append(client.name)
                else:
                    newly_liquidation.append((client.name, ares_name))
                    if not dry_run:
                        client.name = ares_name
                        client.save(update_fields=["name"])

            # 2) insolvencni rejstrik
            raw_stav = company.get("insolvence_stav")
            new_status = raw_stav.lower() if raw_stav in ("AKTIVNI", "HISTORICKY") else ""
            if new_status != client.insolvency_status:
                if new_status == "aktivni":
                    newly_insolvent.append(client.name)
                elif client.insolvency_status == "aktivni" and new_status != "aktivni":
                    resolved_insolvent.append(client.name)
                if not dry_run:
                    client.insolvency_status = new_status
                    client.save(update_fields=["insolvency_status"])

            # 3) OSVC - informativni pohled do zivnostenskeho rejstriku
            if company.get("pravni_forma") == PRAVNI_FORMA_OSVC:
                trade = lookup_trade_register(client.ico)
                if trade and trade.get("provozovny_aktivni") == 0:
                    no_active_provozovna.append((client.name, trade["provozovny_zanikle"]))
                time.sleep(0.2)

            time.sleep(0.2)  # slusne tempo dotazu na verejne ARES API

        if newly_liquidation:
            self.stdout.write(self.style.ERROR(f"\nNOVĚ zjištěno 'v likvidaci' u {len(newly_liquidation)} klientů:"))
            for old_name, new_name in newly_liquidation:
                self.stdout.write(f"  {old_name} -> {new_name}")
        if already_liquidation:
            self.stdout.write(f"\nUž dříve označeno 'v likvidaci' ({len(already_liquidation)}): " + ", ".join(already_liquidation))

        if newly_insolvent:
            self.stdout.write(self.style.ERROR(f"\nNOVĚ zjištěno AKTIVNÍ insolvenční řízení u {len(newly_insolvent)} klientů:"))
            for name in newly_insolvent:
                self.stdout.write(f"  {name}")
        if resolved_insolvent:
            self.stdout.write(self.style.WARNING("\nInsolvenční řízení už není aktivní (bylo) u: " + ", ".join(resolved_insolvent)))

        if no_active_provozovna:
            self.stdout.write(f"\nInformativně - OSVČ bez aktivní provozovny (RŽP, {len(no_active_provozovna)}):")
            for name, zanikle in no_active_provozovna:
                self.stdout.write(f"  {name} (0 aktivních, {zanikle} zaniklých)")

        self.stdout.write(self.style.SUCCESS(
            f"\nHotovo{' (dry-run, nic se neulozilo)' if dry_run else ''}: zkontrolováno {clients.count()} "
            f"aktivních klientů s ICO, {not_found} nenalezeno v ARES, "
            f"{len(newly_liquidation)} nově 'v likvidaci', {len(newly_insolvent)} nově v aktivní insolvenci."
        ))
