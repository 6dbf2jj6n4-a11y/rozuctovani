"""
Diagnostika: vypise VSECHNY klice (vsech klientu) u polozek "odvoz
komunalniho odpadu NJ" a "uklidove sluzby spolecnych prostor NJ" -
hledame, jestli nejaky klient typu Pevna castka (s Odecist z celkoveho
nakladu) nespotrebuje cely zadany Naklad, takze vahovym klicum
(napr. Aktiv Novostav) zbyde 0 Kc.

Pouziti:
  python manage.py diag_ostatni_nj
"""
from django.core.management.base import BaseCommand

from core.models import ServicePoolItem


ITEM_NAMES = ["odvoz komunálního odpadu NJ", "úklidové služby společných prostor NJ"]


class Command(BaseCommand):
    help = "Vypíše všechny klíče u vybraných OSTATNÍ položek NJ."

    def handle(self, *args, **options):
        for name in ITEM_NAMES:
            item = ServicePoolItem.objects.filter(name=name).first()
            if item is None:
                self.stdout.write(self.style.ERROR(f'Položka "{name}" nenalezena.'))
                continue

            self.stdout.write(self.style.WARNING(f"\n--- {item} ---"))
            keys = item.allocation_keys.select_related("client_card__client").all()
            fixed_total = 0
            for key in keys:
                marker = ""
                if key.allocation_type == "fixed_amount":
                    marker = f"  <-- PEVNÁ ČÁSTKA, odečíst_z_poolu={key.deduct_from_pool}"
                    if key.deduct_from_pool:
                        fixed_total += key.value or 0
                self.stdout.write(
                    f"  {key.client_card.client.name}: {key.get_allocation_type_display()} "
                    f"hodnota={key.value} fakturovat={key.is_billed}{marker}"
                )
            self.stdout.write(f"  SOUČET pevných částek (odečítaných z poolu): {fixed_total} Kč")
