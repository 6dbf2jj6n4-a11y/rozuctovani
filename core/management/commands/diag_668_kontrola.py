"""
Diagnostika (jen cteni): zkontroluje, jestli klice na meridlech 668NT/668VT
(FM, polozka "odběr EAN 668 FM") omylem neskoncily pod jinou polozkou
(napr. "hlavní odběr elektro FM") kvuli fallback hledani podle nazvu
v import_klice_elektro.py - 668NT/668VT nemaji parent_meter hierarchii,
takze primy i korenovy match selze a fallback by je mohl chybne prirait
jine polozce se stejnou tridou.

Pouziti:
  python manage.py diag_668_kontrola
"""
from django.core.management.base import BaseCommand

from core.models import AllocationKey, Meter, Site


class Command(BaseCommand):
    help = "Zkontroluje, na jaké ServicePoolItem jsou navázané klíče s měřidlem 668NT/668VT."

    def handle(self, *args, **options):
        site = Site.objects.filter(name__icontains="FM").first()
        if not site:
            self.stdout.write(self.style.ERROR("Areál FM nenalezen."))
            return

        for code in ["668NT", "668VT"]:
            meter = Meter.objects.filter(site=site, code=code).first()
            if meter is None:
                self.stdout.write(f"{code}: měřidlo nenalezeno")
                continue
            self.stdout.write(self.style.WARNING(f"\n=== klíče na měřidle {code} ==="))
            keys = AllocationKey.objects.filter(meter=meter).select_related(
                "client_card__client", "service_item"
            )
            for key in keys:
                self.stdout.write(
                    f"  {key.client_card.client.name}: položka={key.service_item.name!r} "
                    f"typ={key.allocation_type} hodnota={key.value} (key id={key.id})"
                )
