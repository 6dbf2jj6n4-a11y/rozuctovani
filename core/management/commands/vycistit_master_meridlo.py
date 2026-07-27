"""
Vynuluje pole "Master měřidlo" (parent_meter) u vsech meridel, ktera ho
maji nastavene na meridlo E_CELKEM - to uz se v realnem provozu nepouziva
(historicky pozustatek z importnich skriptu, viz napr.
core/management/commands/import_klice_elektro.py). Pole parent_meter se
NIKDE ve skutecnem vypoctu vyuctovani (billing/engine.py) ani v
auditovaci tabulce Detail (billing/key_detail.py) nepouziva - jde jen
o bookkeeping, takze tahle oprava nema zadny vliv na uz spocitane
vyuctovani, jen zpresnuje data.

Pouziti:
  python manage.py vycistit_master_meridlo
  python manage.py vycistit_master_meridlo --dry-run
"""
from django.core.management.base import BaseCommand

from core.models import Meter


class Command(BaseCommand):
    help = 'Vynuluje "Master měřidlo" (parent_meter) u měřidel navázaných na E_CELKEM.'

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se změnilo")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        master = Meter.objects.filter(code="E_CELKEM").first()
        if master is None:
            self.stdout.write(self.style.WARNING('Měřidlo s kódem "E_CELKEM" v databázi neexistuje - nic k opravě.'))
            return

        affected = Meter.objects.filter(parent_meter=master)
        count = affected.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("Žádné měřidlo nemá E_CELKEM jako Master měřidlo."))
            return

        for meter in affected:
            self.stdout.write(f"{meter} (#{meter.pk}, areál {meter.site}): Master měřidlo -> prázdné")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n--dry-run: {count} měřidel by bylo opraveno, nic se neuložilo."))
            return

        updated = affected.update(parent_meter=None)
        self.stdout.write(self.style.SUCCESS(f"\nOpraveno {updated} měřidel."))
