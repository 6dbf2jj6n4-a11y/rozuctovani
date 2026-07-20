"""
Doplni chybejici udaje aktivnich klientu z ARES a Registru platcu DPH -
totez, co dela tlacitko "Nacist z ARES" v adminu, jen hromadne pro vsechny
aktivni klienty a jen pro prazdna pole (nic existujiciho se neprepisuje).

Pouziti:
  python manage.py doplnit_ares
  python manage.py doplnit_ares --dry-run
"""
import time

from django.core.management.base import BaseCommand

from core.ares_client import lookup_company, lookup_registry
from core.dph_registry import lookup_vat_payer
from core.models import Client


class Command(BaseCommand):
    help = "Doplní chybějící údaje aktivních klientů z ARES/Registru DPH (jen prázdná pole)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se změnilo")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        clients = Client.objects.filter(is_active=True).exclude(ico="").order_by("name")

        updated_count = 0
        no_change_count = 0
        no_ico_data_count = 0

        for client in clients:
            changed = []

            company = lookup_company(client.ico)
            if company:
                if not client.dic and company["dic"]:
                    client.dic = company["dic"]
                    changed.append(f"dic={company['dic']}")
                    if not client.vat_payer:
                        client.vat_payer = True
                        changed.append("vat_payer=True")
                if not client.street and company["street"]:
                    client.street = company["street"]
                    changed.append(f"street={company['street']}")
                if not client.street_number and company["street_number"]:
                    client.street_number = company["street_number"]
                    changed.append(f"street_number={company['street_number']}")
                if not client.zip_code and company["zip_code"]:
                    client.zip_code = company["zip_code"]
                    changed.append(f"zip_code={company['zip_code']}")
                if not client.city and company["city"]:
                    client.city = company["city"]
                    changed.append(f"city={company['city']}")

            registry = lookup_registry(client.ico)
            if registry:
                if not client.registry_court and registry["court"]:
                    client.registry_court = registry["court"]
                    changed.append(f"registry_court={registry['court']}")
                if not client.registry_section and registry["section"]:
                    client.registry_section = registry["section"]
                    changed.append(f"registry_section={registry['section']}")
                if not client.registry_insert and registry["insert"]:
                    client.registry_insert = registry["insert"]
                    changed.append(f"registry_insert={registry['insert']}")

            vat = lookup_vat_payer(client.ico)
            if vat and vat.get("accounts"):
                acc = vat["accounts"][0]
                if not client.bank_account and acc.get("cislo_uctu"):
                    client.bank_account = acc["cislo_uctu"]
                    changed.append(f"bank_account={acc['cislo_uctu']}")
                if not client.bank_code and acc.get("kod_banky"):
                    client.bank_code = acc["kod_banky"]
                    changed.append(f"bank_code={acc['kod_banky']}")
                if not client.bank_name and acc.get("nazev_banky"):
                    client.bank_name = acc["nazev_banky"]
                    changed.append(f"bank_name={acc['nazev_banky']}")

            if not company and not registry and not (vat and vat.get("accounts")):
                no_ico_data_count += 1
                self.stdout.write(f"  {client.name} (IČO {client.ico}): v ARES/DPH registru nic nenalezeno")
            elif changed:
                self.stdout.write(f"  {client.name}: {', '.join(changed)}")
                if not dry_run:
                    client.save()
                updated_count += 1
            else:
                no_change_count += 1

            time.sleep(0.2)  # slusne tempo dotazu na verejna API

        self.stdout.write(self.style.SUCCESS(
            f"\nHotovo{' (dry-run, nic se neulozilo)' if dry_run else ''}: "
            f"{updated_count} klientů doplněno, {no_change_count} už mělo vše vyplněné, "
            f"{no_ico_data_count} nenalezeno v ARES/DPH registru "
            f"(z {clients.count()} aktivních klientů s IČO)."
        ))
