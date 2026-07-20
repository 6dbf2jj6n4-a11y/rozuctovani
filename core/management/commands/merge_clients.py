"""
Slouci dva duplicitni zaznamy Klienta do jednoho - vsechny Karty klienta
a Smlouvy patrici klientovi --remove se preradi pod klienta --keep,
a klient --remove se pak smaze.

Pouziti:
  python manage.py merge_clients --keep 7 --remove 32
  python manage.py merge_clients --keep 7 --remove 32 --dry-run
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Client, ClientCard, Contract


class Command(BaseCommand):
    help = "Sloucí dva duplicitní záznamy Klienta (přeřadí karty/smlouvy, smaže duplicitu)."

    def add_arguments(self, parser):
        parser.add_argument("--keep", type=int, required=True, help="ID klienta, který zůstane")
        parser.add_argument("--remove", type=int, required=True, help="ID klienta, který se smaže")
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se stalo")

    def handle(self, *args, **options):
        keep_id = options["keep"]
        remove_id = options["remove"]
        dry_run = options["dry_run"]

        if keep_id == remove_id:
            raise CommandError("--keep a --remove musí být různá ID.")

        try:
            keep = Client.objects.get(pk=keep_id)
        except Client.DoesNotExist:
            raise CommandError(f"Klient --keep={keep_id} neexistuje.")
        try:
            remove = Client.objects.get(pk=remove_id)
        except Client.DoesNotExist:
            raise CommandError(f"Klient --remove={remove_id} neexistuje.")

        cards = list(ClientCard.objects.filter(client=remove))
        contracts = list(Contract.objects.filter(client=remove))

        self.stdout.write(f"Ponechat: {keep} (#{keep.pk}, kód {keep.code})")
        self.stdout.write(f"Smazat:   {remove} (#{remove.pk}, kód {remove.code})")
        self.stdout.write(f"Karty klienta k přeřazení: {len(cards)}")
        for c in cards:
            self.stdout.write(f"  - {c} (#{c.pk})")
        self.stdout.write(f"Smlouvy k přeřazení: {len(contracts)}")
        for c in contracts:
            self.stdout.write(f"  - {c} (#{c.pk})")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run - nic se nezměnilo."))
            return

        with transaction.atomic():
            for c in cards:
                c.client = keep
                c.save(update_fields=["client"])
            for c in contracts:
                c.client = keep
                c.save(update_fields=["client"])
            remove.delete()

        self.stdout.write(self.style.SUCCESS(
            f"Hotovo: přeřazeno {len(cards)} karet a {len(contracts)} smluv pod klienta #{keep.pk}, "
            f"klient #{remove_id} smazán."
        ))
