"""
Přepíše mailový kontakt (Client.contact_email) u všech AKTIVNÍCH klientů
hodnotou z adresáře ABRA Flexi (evidence "adresar", pole "email") -
párování podle IČO, stejně jako core/management/commands/porovnat_emaily_flexi.py.

Klienty, které se nepodaří dohledat ve Flexi podle IČO, nebo u kterých
je Flexi pole "email" prázdné, přeskočí (aby nedošlo ke smazání už
existujícího kontaktu prázdnou hodnotou) - takové případy vypíše zvlášť.

Použití:
  python manage.py aktualizovat_maily_flexi
  python manage.py aktualizovat_maily_flexi --dry-run
"""
from django.core.management.base import BaseCommand, CommandError

from core.flexi_client import FlexiAPIError, FlexiClient
from core.models import Client


def _clean_ico(value):
    return (value or "").strip().lstrip("0") or (value or "").strip()


class Command(BaseCommand):
    help = "Přepíše e-mail aktivních Klientů hodnotou z adresáře ve Flexi (párováno podle IČO)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se změnilo")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        try:
            flexi_client = FlexiClient()
            records = flexi_client.list_records(
                "adresar",
                extra_params={"limit": 0, "detail": "full"},
            )
        except KeyError as e:
            raise CommandError(f"Chybí env proměnná {e} (FLEXI_URL, FLEXI_COMPANY, FLEXI_USER, FLEXI_PASS)")
        except FlexiAPIError as e:
            raise CommandError(f"Flexi API chyba {e.status_code}: {e.response_body}")

        flexi_by_ico = {}
        for rec in records:
            ico = _clean_ico(rec.get("ic"))
            if ico:
                flexi_by_ico[ico] = rec

        clients = Client.objects.filter(is_active=True).exclude(ico="").order_by("name")

        updated, unchanged, no_flexi_email, not_found = 0, 0, 0, 0
        for client in clients:
            ico = _clean_ico(client.ico)
            rec = flexi_by_ico.get(ico)
            if rec is None:
                not_found += 1
                self.stdout.write(self.style.WARNING(f"{client.name}: IČO {client.ico} nenalezeno ve Flexi - přeskočeno"))
                continue

            flexi_email = (rec.get("email") or "").strip()
            if not flexi_email:
                no_flexi_email += 1
                self.stdout.write(self.style.WARNING(f"{client.name}: Flexi nemá vyplněný e-mail - ponechán stávající"))
                continue

            our_email = (client.contact_email or "").strip()
            if our_email.lower() == flexi_email.lower():
                unchanged += 1
                continue

            self.stdout.write(f"{client.name}: {our_email or '(prázdné)'!r} -> {flexi_email!r}")
            updated += 1
            if not dry_run:
                client.contact_email = flexi_email
                client.save(update_fields=["contact_email"])

        prefix = "--dry-run: " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"\n{prefix}Aktualizováno {updated}, beze změny {unchanged}, "
            f"bez e-mailu ve Flexi {no_flexi_email}, nenalezeno ve Flexi {not_found}."
        ))
