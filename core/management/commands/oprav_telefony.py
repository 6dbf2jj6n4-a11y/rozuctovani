"""
Sjednoti format telefonnich cisel u klientu.

Samotny prevod NEDELA tenhle prikaz - deleguje na
core.models.normalizovat_telefon, aby platilo jedno pravidlo vsude
(ulozeni klienta v adminu, importy i tenhle prikaz). Cilovy tvar je
"+420 123 456 789"; napsana predvolba (420/421) se respektuje a cislo
bez predvolby se doplnuje jen u ceskych mobilu (6xx/7xx), kde je zeme
jista - viz docstring te funkce.

Puvodne mel prikaz vlastni prevod na "+420 777123456", ktery navic vzdy
predpokladal ceskou predvolbu; po dohode s Danielem 2026-08-19 (format
s mezerami + pozor na slovenska cisla) by tenhle format prepisoval.

Pouziti:
  python manage.py oprav_telefony --dry-run
  python manage.py oprav_telefony
"""
import re

from django.core.management.base import BaseCommand

from core.models import Client, normalizovat_telefon


# Cilovy tvar, na ktery normalizovat_telefon prevadi: "+420 123 456 789",
# u cisel bez rozpoznatelne predvolby "123 456 789" (trojice jsou vzdy).
CILOVY_TVAR = re.compile(r"^(\+\d{3} )?\d{3} \d{3} \d{3}$")


def normalize_phone(raw):
    """Vrati (novy_tvar, None) nebo (None, duvod_preskoceni).

    Tenka obalka nad core.models.normalizovat_telefon. Rozlisuje dva
    duvody, proc se nic nemeni - cislo uz tvar MA, nebo ho nejde
    rozpoznat. Driv to splyvalo v jedno a uz srovnana cisla se hlasila
    jako "nerozpoznana", coz zbytecne desilo."""
    novy = normalizovat_telefon(raw)
    if novy != raw:
        return novy, None
    if CILOVY_TVAR.match(raw.strip()):
        return None, None       # uz je srovnane, neni co resit
    return None, "nerozpoznaný tvar - nechávám, jak je"


class Command(BaseCommand):
    help = "Sjednotí formát telefonu klientů na '+420 123 456 789'."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se změnilo")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        changed_count = 0
        ok_count = 0
        skipped = []

        # "+420 " se driv preskakovalo; dneska ho normalizovat_telefon
        # umi vycistit na prazdno (klient bez telefonu ma mit pole
        # prazdne), takze se do prohlidky pousti taky. Daniel 2026-08-24.
        for client in Client.objects.exclude(contact_phone=""):
            new_phone, skip_reason = normalize_phone(client.contact_phone)
            if skip_reason:
                skipped.append((client, skip_reason))
                continue
            if new_phone is None:
                ok_count += 1
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
            f"upraveno {changed_count}, už bylo v pořádku {ok_count}, "
            f"nerozpoznáno {len(skipped)}."
        ))
