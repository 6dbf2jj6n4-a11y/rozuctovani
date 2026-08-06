"""
Sjednoti format telefonnich cisel u klientu na "+420 XXXXXXXXX" (predvolba,
mezera, 9-mistne cislo bez dalsich mezer/pomlcek). Zvladne ruzne vstupni
tvary ("420777123456", "+420 777 123 456", "00420777123456", "777123456"
bez predvolby...) - vytahne jen cislice, odstrani uvodni "420"/"00420" pokud
tam je, a co zbyde musi byt presne 9-mistne ceske cislo. Kdyz po ocisteni
nevyjde 9 cislic, cislo se preskoci a vypise se k rucni kontrole (aby se
nezapsalo neco spatne).

Pouziti:
  python manage.py oprav_telefony --dry-run
  python manage.py oprav_telefony
"""
import re

from django.core.management.base import BaseCommand

from core.models import Client


def normalize_phone(raw):
    """Vrati (novy_tvar, None) nebo (None, duvod_preskoceni)."""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00420"):
        digits = digits[5:]
    elif digits.startswith("420") and len(digits) > 9:
        digits = digits[3:]
    if len(digits) != 9:
        return None, f"po ocisteni {len(digits)} cislic ({digits!r}), ocekavano 9"
    return f"+420 {digits}", None


class Command(BaseCommand):
    help = "Sjednotí formát telefonu klientů na '+420 XXXXXXXXX'."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se změnilo")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        changed_count = 0
        skipped = []

        for client in Client.objects.exclude(contact_phone="").exclude(contact_phone="+420 "):
            new_phone, skip_reason = normalize_phone(client.contact_phone)
            if skip_reason:
                skipped.append((client, skip_reason))
                continue
            if new_phone == client.contact_phone:
                continue
            self.stdout.write(f"{client.name}: {client.contact_phone!r} -> {new_phone!r}")
            changed_count += 1
            if not dry_run:
                client.contact_phone = new_phone
                client.save(update_fields=["contact_phone"])

        for client, reason in skipped:
            self.stdout.write(self.style.WARNING(
                f"PŘESKOČENO {client.name}: {client.contact_phone!r} ({reason})"
            ))

        self.stdout.write(self.style.SUCCESS(
            f"\nHotovo{' (dry-run, nic se neulozilo)' if dry_run else ''}: "
            f"upraveno {changed_count}, přeskočeno {len(skipped)}."
        ))
