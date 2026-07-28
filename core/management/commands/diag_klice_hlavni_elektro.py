"""
Diagnostika pred smazanim meridla E_CELKEM: zjisti, jestli nejaky Klic
u polozek "Hlavni odber elektro FM/NJ" pouziva typ "Podruzne meridlo"
(SUBMETER) - takovy klic by smazanim E_CELKEM prestal fungovat spravne
(viz konverzace).

Pouziti:
  python manage.py diag_klice_hlavni_elektro
"""
from django.core.management.base import BaseCommand

from core.models import AllocationKey, ServicePoolItem


class Command(BaseCommand):
    help = "Zkontroluje typy klíčů u položek Hlavní odběr elektro FM/NJ."

    def handle(self, *args, **options):
        items = ServicePoolItem.objects.filter(name__icontains="hlavní odběr elektro")
        if not items:
            self.stdout.write(self.style.WARNING('Nenalezena žádná položka s názvem obsahujícím "hlavní odběr elektro".'))
            return

        any_submeter = False
        for item in items:
            self.stdout.write(self.style.WARNING(f"\n--- {item} (měřidlo položky: {item.meter}) ---"))
            keys = item.allocation_keys.select_related("client_card__client", "meter").all()
            if not keys:
                self.stdout.write("  žádné klíče")
                continue
            for key in keys:
                flag = ""
                if key.allocation_type == AllocationKey.AllocationType.SUBMETER:
                    flag = "  <-- PODRUŽNÉ MĚŘIDLO"
                    any_submeter = True
                self.stdout.write(
                    f"  {key.client_card.client.name}: {key.get_allocation_type_display()} "
                    f"(měřidlo klíče: {key.meter}){flag}"
                )

        self.stdout.write("")
        if any_submeter:
            self.stdout.write(self.style.WARNING(
                "Alespoň jeden klíč používá Podružné měřidlo - smazání E_CELKEM by tento klíč pokazilo."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "Žádný klíč nepoužívá Podružné měřidlo - smazání E_CELKEM (a přechod položky na výpočet "
                "podle vážených klíčů) je matematicky bezpečné, výsledek vyjde stejně."
            ))
