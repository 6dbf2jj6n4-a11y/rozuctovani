"""
Opravi klienty, jejichz ICO ma min nez 8 znaku (typicky kdyz se pri
importu/rucnim zadani ztratila uvodni nula - ceske ICO ma vzdy 8 cislic).
Chybejici nuly doplni zleva (zfill) a pak pro tyto opravene klienty
znovu nacte udaje z ARES - na rozdil od `doplnit_ares` tady se
prepisuji i jiz vyplnena pole (nazev, adresa, DIC, rejstrik), protoze
byla puvodne svazana se spatnym ICO a nelze jim duverovat.
Bankovni udaje (Registr DPH) se nedotykaji.

Pouziti:
  python manage.py oprav_kratka_ica
  python manage.py oprav_kratka_ica --dry-run
"""
import time

from django.core.management.base import BaseCommand

from core.ares_client import lookup_company, lookup_registry
from core.models import Client


class Command(BaseCommand):
    help = "Doplní chybějící úvodní nuly u ICO kratších než 8 znaků a obnoví jejich údaje z ARES."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se změnilo")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        short_ico_clients = [c for c in Client.objects.exclude(ico="") if len(c.ico.strip()) < 8]

        if not short_ico_clients:
            self.stdout.write(self.style.SUCCESS("Žádný klient nemá ICO kratší než 8 znaků."))
            return

        for client in short_ico_clients:
            old_ico = client.ico.strip()
            new_ico = old_ico.zfill(8)
            self.stdout.write(f"\n{client.name}: ICO {old_ico!r} -> {new_ico!r}")

            if not dry_run:
                client.ico = new_ico
                client.save(update_fields=["ico"])

            company = lookup_company(new_ico)
            registry = lookup_registry(new_ico)

            if not company and not registry:
                self.stdout.write(self.style.WARNING(f"  v ARES pro {new_ico} nic nenalezeno - ICO opraveno, zbytek beze změny."))
                time.sleep(0.2)
                continue

            changed = []
            if company:
                for field, value in [
                    ("name", company["name"]), ("dic", company["dic"]),
                    ("street", company["street"]), ("street_number", company["street_number"]),
                    ("zip_code", company["zip_code"]), ("city", company["city"]),
                ]:
                    if value and getattr(client, field) != value:
                        changed.append(f"{field}: {getattr(client, field)!r} -> {value!r}")
                        if not dry_run:
                            setattr(client, field, value)
                if company["dic"] and not client.vat_payer:
                    changed.append("vat_payer: False -> True")
                    if not dry_run:
                        client.vat_payer = True

            if registry:
                for field, value in [
                    ("registry_court", registry["court"]), ("registry_section", registry["section"]),
                    ("registry_insert", registry["insert"]),
                ]:
                    if value and getattr(client, field) != value:
                        changed.append(f"{field}: {getattr(client, field)!r} -> {value!r}")
                        if not dry_run:
                            setattr(client, field, value)

            if changed:
                self.stdout.write("  " + " | ".join(changed))
                if not dry_run:
                    client.save()
            else:
                self.stdout.write("  ARES údaje už odpovídají, jen ICO bylo opraveno.")

            time.sleep(0.2)  # slusne tempo dotazu na verejne ARES API

        self.stdout.write(self.style.SUCCESS(
            f"\nHotovo{' (dry-run, nic se neulozilo)' if dry_run else ''}: "
            f"opraveno ICO u {len(short_ico_clients)} klientů."
        ))
