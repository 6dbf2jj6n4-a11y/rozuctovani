"""
Zalozi Klice (AllocationKey) na polozce "teplo - spotreba pelet NJ" -
data prevzata primo ze zdrojoveho souboru Klice_teplo_NJ.xlsx (T_CELKEM
= radiatory, T_SPOLECNA = osoby), ale POUZITA JE HODNOTA "Jednotek"
(syrovy pocet), NE "Podil" (predem spocitany zlomek) - viz konverzace:
takto se pomer mezi klienty prepocita sam pri zmene poctu klientu/
radiatoru/osob, bez nutnosti rucne prepocitavat zlomky (na rozdil od
"hlavni odber teplo NJ", kde je v DB ulozeny uz hotovy Podil).

Oba typy (radiatory i osoby) jsou weighted_count (stejne jako u "hlavni
odber teplo NJ" - NJ kody neobsahuji "TUV", takze zadny klic tam neni
person_count). "FinTok" ve zdrojovem souboru (zapnuto/vypnuto) se
promita do AllocationKey.is_billed.

Pouziti:
  python manage.py nastavit_klice_pelety_nj
  python manage.py nastavit_klice_pelety_nj --dry-run
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.models import AllocationKey, ClientCard, ServicePoolItem

# (PopisKarty, T_CELKEM Jednotek, T_CELKEM FinTok, T_SPOLECNA Jednotek, T_SPOLECNA FinTok)
# Zdroj: /Users/daniel/Desktop/RenteX/Klíče_teplo_NJ.xlsx (sloupce Jednotek + FinTok)
DATA = [
    ("Karta CSE 1 NJ", 1, True, 1, True),
    ("Karta FSLCZ 2026 - 1", 0, True, 1, True),
    ("Karta MAKER 2025 - 1", 2, False, 1, False),
    ("Karta MVACTIVE 2025 - 1", 4, True, 2, True),
    ("Karta ONEKLIMA 2026 - 1", 3, True, 5, True),
    ("Karta EVUM 2026 - 1", 0, True, 2, True),
    ("Karta AKTIVNOV 2026 - 1", 2, True, 2, True),
    ("Karta DELPHIA 2026 - 1", 1, False, 1, False),
    ("Karta MASTRCRANE 2026 - 1", 1, False, 1, False),
    ("Karta GNES 2026 - 1", 1, False, 1, False),
    ("Karta BURNTECH 2026 - 2", 3, True, 3, True),
    ("Karta INNEXUM 2026 - 1", 2, False, 2, False),
]

ITEM_NAME = "teplo - spotřeba pelet NJ"


class Command(BaseCommand):
    help = f'Založí Klíče (radiátory + osoby, syrové hodnoty) na položce "{ITEM_NAME}".'

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se vytvořilo")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        item = ServicePoolItem.objects.filter(name=ITEM_NAME).first()
        if item is None:
            self.stdout.write(self.style.ERROR(f'Položka "{ITEM_NAME}" nenalezena.'))
            return

        existing = AllocationKey.objects.filter(service_item=item).count()
        if existing:
            self.stdout.write(self.style.WARNING(
                f'Položka "{ITEM_NAME}" už má {existing} klíč(ů) - pokud spouštíš znovu, zkontroluj duplicity ručně.'
            ))

        created = 0
        for card_desc, radiatory, radiatory_billed, osoby, osoby_billed in DATA:
            card = ClientCard.objects.filter(description=card_desc, is_active=True).first()
            if card is None:
                self.stdout.write(self.style.WARNING(f"Karta nenalezena: {card_desc}"))
                continue

            if radiatory > 0:
                self.stdout.write(
                    f"{card_desc}: radiátory={radiatory} (fakturovat={radiatory_billed})"
                )
                if not dry_run:
                    AllocationKey.objects.create(
                        client_card=card, service_item=item,
                        allocation_type=AllocationKey.AllocationType.WEIGHTED_COUNT,
                        value=Decimal(radiatory), is_billed=radiatory_billed,
                    )
                created += 1

            if osoby > 0:
                self.stdout.write(
                    f"{card_desc}: osoby={osoby} (fakturovat={osoby_billed})"
                )
                if not dry_run:
                    AllocationKey.objects.create(
                        client_card=card, service_item=item,
                        allocation_type=AllocationKey.AllocationType.WEIGHTED_COUNT,
                        value=Decimal(osoby), is_billed=osoby_billed,
                    )
                created += 1

        prefix = "--dry-run: " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"\n{prefix}Klíčů k vytvoření: {created}."))
