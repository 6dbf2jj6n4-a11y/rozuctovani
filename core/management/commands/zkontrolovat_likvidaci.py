"""
Mesicni kontrola rizika: projde aktivni klienty s vyplnenym ICO a overi
v ARES, jestli se u nazvu firmy neobjevilo "v likvidaci" - to je signal,
ze dalsi spoluprace s klientem muze byt riziko (napr. nebude platit
najem/sluzby).

Pokud ARES vraci nazev s "v likvidaci" a nas ulozeny nazev to jeste
neobsahuje, aktualizuje se nazev klienta na aktualni znenim z ARES -
diky tomu se klient hned zvyrazni cervene v seznamu klientu v adminu
(viz ClientAdmin.name_display).

Pouziti:
  python manage.py zkontrolovat_likvidaci
  python manage.py zkontrolovat_likvidaci --dry-run
"""
import time

from django.core.management.base import BaseCommand

from core.ares_client import lookup_company
from core.models import Client


class Command(BaseCommand):
    help = "Zkontroluje v ARES, jestli se u aktivních klientů neobjevilo 'v likvidaci' v názvu."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se změnilo")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        clients = Client.objects.filter(is_active=True).exclude(ico="").order_by("name")

        newly_flagged = []
        already_flagged = []
        not_found = 0

        for client in clients:
            company = lookup_company(client.ico)
            if not company or not company.get("name"):
                not_found += 1
                time.sleep(0.2)
                continue

            ares_name = company["name"]
            if "v likvidaci" in ares_name.lower():
                if "v likvidaci" in client.name.lower():
                    already_flagged.append(client.name)
                else:
                    newly_flagged.append((client.name, ares_name))
                    if not dry_run:
                        client.name = ares_name
                        client.save(update_fields=["name"])

            time.sleep(0.2)  # slusne tempo dotazu na verejne ARES API

        if newly_flagged:
            self.stdout.write(self.style.ERROR(f"\nNOVĚ zjištěno 'v likvidaci' u {len(newly_flagged)} klientů:"))
            for old_name, new_name in newly_flagged:
                self.stdout.write(f"  {old_name} -> {new_name}")
        if already_flagged:
            self.stdout.write(f"\nUž dříve označeno 'v likvidaci' ({len(already_flagged)}): " + ", ".join(already_flagged))

        self.stdout.write(self.style.SUCCESS(
            f"\nHotovo{' (dry-run, nic se neulozilo)' if dry_run else ''}: zkontrolováno {clients.count()} "
            f"aktivních klientů s ICO, {not_found} nenalezeno v ARES, "
            f"{len(newly_flagged)} nově označeno jako 'v likvidaci'."
        ))
