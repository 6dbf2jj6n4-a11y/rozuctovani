"""
Smaze meridlo(a) s kodem "E_CELKEM" (typicky jedno na FM, jedno na NJ -
kod neni globalne unikatni, jen v ramci arealu) - uz se nepouziva,
viz konverzace (Hlavni odber elektro FM/NJ v Nakladech uz predstavuje
stejne cislo, co drivejsi odecet E_CELKEM).

Pred smazanim:
  1. Vypise, ktere Polozky zasobniku ho maji jako sve Meridlo (po smazani
     se tato vazba automaticky vynuluje - SET_NULL, polozka pak pocita
     podle vazenych klicu, ne podle spotreby na meridle).
  2. Vycisti "Master meridlo" (parent_meter) u VSECH meridel, ktera na
     nej odkazuji (parent_meter ma on_delete=PROTECT, jinak by smazani
     selhalo) - narozdil od drivejsiho vycistit_master_meridlo.py, ktery
     omylem vzal jen prvni nalezene E_CELKEM (fix zde resi obe/vsechna).

Pouziti:
  python manage.py smazat_meridlo_e_celkem
  python manage.py smazat_meridlo_e_celkem --dry-run
"""
from django.core.management.base import BaseCommand

from core.models import Meter, ServicePoolItem


class Command(BaseCommand):
    help = 'Smaže měřidlo(a) E_CELKEM (na všech areálech, kde existuje).'

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se stalo")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        meters = list(Meter.objects.filter(code="E_CELKEM"))
        if not meters:
            self.stdout.write(self.style.WARNING('Žádné měřidlo s kódem "E_CELKEM" v databázi neexistuje.'))
            return

        for meter in meters:
            self.stdout.write(self.style.WARNING(f"\n--- {meter} (#{meter.pk}, areál {meter.site}) ---"))

            items = ServicePoolItem.objects.filter(meter=meter)
            for item in items:
                self.stdout.write(f"  Položka '{item}' o něj přijde jako o Měřidlo (přejde na výpočet dle klíčů).")

            children = Meter.objects.filter(parent_meter=meter)
            for child in children:
                self.stdout.write(f"  Měřidlo '{child}' mělo E_CELKEM jako Master měřidlo -> vynuluje se.")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n--dry-run: {len(meters)} měřidel by bylo smazáno, nic se neuložilo."))
            return

        Meter.objects.filter(parent_meter__in=meters).update(parent_meter=None)
        count, _ = Meter.objects.filter(pk__in=[m.pk for m in meters]).delete()
        self.stdout.write(self.style.SUCCESS(f"\nSmazáno měřidel: {len(meters)}."))
