"""
Diagnostika pred smazanim "souhrnneho" meridla (E_CELKEM/T_CELKEM/
W_CELKEM apod.): zjisti, jestli nejaky Klic u polozek, ktere ho maji
jako sve Meridlo, pouziva typ "Podruzne meridlo" (SUBMETER) - takovy
klic by smazanim meridla prestal fungovat spravne (viz konverzace).

Pouziti:
  python manage.py diag_klice_hlavni_elektro E_CELKEM
  python manage.py diag_klice_hlavni_elektro T_CELKEM W_CELKEM
"""
from django.core.management.base import BaseCommand

from core.models import AllocationKey, Meter, ServicePoolItem


class Command(BaseCommand):
    help = "Zkontroluje typy klíčů u položek, které mají zadaný kód měřidla jako své Měřidlo."

    def add_arguments(self, parser):
        parser.add_argument("kody", nargs="+", type=str, help="Kódy měřidel, např. E_CELKEM T_CELKEM W_CELKEM")

    def handle(self, *args, **options):
        any_submeter_total = False
        for kod in options["kody"]:
            meters = Meter.objects.filter(code=kod)
            if not meters:
                self.stdout.write(self.style.WARNING(f'\nMěřidlo s kódem "{kod}" v databázi neexistuje.'))
                continue

            items = ServicePoolItem.objects.filter(meter__in=meters)
            if not items:
                self.stdout.write(self.style.WARNING(f'\nŽádná položka nemá "{kod}" nastavené jako své Měřidlo.'))
                continue

            for item in items:
                self.stdout.write(self.style.WARNING(f"\n--- {item} (měřidlo položky: {item.meter}) ---"))
                keys = item.allocation_keys.select_related("client_card__client", "meter").all()
                if not keys:
                    self.stdout.write("  žádné klíče")
                    continue
                for key in keys:
                    flag = ""
                    if key.allocation_type == AllocationKey.AllocationType.WEIGHTED_COUNT:
                        flag = "  <-- PODRUŽNÉ MĚŘIDLO"
                        any_submeter_total = True
                    self.stdout.write(
                        f"  {key.client_card.client.name}: {key.get_allocation_type_display()} "
                        f"(měřidlo klíče: {key.meter}){flag}"
                    )

        self.stdout.write("")
        if any_submeter_total:
            self.stdout.write(self.style.WARNING(
                "Alespoň jeden klíč používá Podružné měřidlo - smazání by tento klíč pokazilo."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "Žádný klíč nepoužívá Podružné měřidlo - smazání (a přechod položky na výpočet "
                "podle vážených klíčů) je matematicky bezpečné, výsledek vyjde stejně."
            ))
