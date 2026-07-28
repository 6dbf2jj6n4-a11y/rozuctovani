"""
Smaze meridlo(a) se zadanymi kody (napr. E_CELKEM, T_CELKEM, W_CELKEM -
kazdy kod neni globalne unikatni, jen v ramci arealu, takze na FM i NJ
muze pod stejnym kodem existovat samostatny zaznam) - uz se nepouzivaji,
viz konverzace (Hlavni odber elektro/teplo/voda FM/NJ v Nakladech uz
predstavuje stejne cislo, co drivejsi odecet na techto meridlech).

Pred smazanim:
  1. Vypise, ktere Polozky zasobniku ho maji jako sve Meridlo (po smazani
     se tato vazba automaticky vynuluje - SET_NULL, polozka pak pocita
     podle vazenych klicu, ne podle spotreby na meridle).
  2. Vycisti "Master meridlo" (parent_meter) u VSECH meridel, ktera na
     nej odkazuji (parent_meter ma on_delete=PROTECT, jinak by smazani
     selhalo).

Pred spustenim doporucuji overit bezpecnost pres
core/management/commands/diag_klice_hlavni_elektro.py (zadny Klic
typu "Podruzne meridlo" by na mazana meridla nemel ukazovat).

Pouziti:
  python manage.py smazat_meridlo_e_celkem E_CELKEM
  python manage.py smazat_meridlo_e_celkem E_CELKEM T_CELKEM W_CELKEM --dry-run
"""
from django.core.management.base import BaseCommand

from core.models import Meter, ServicePoolItem


class Command(BaseCommand):
    help = "Smaže měřidlo(a) se zadanými kódy (na všech areálech, kde existují)."

    def add_arguments(self, parser):
        parser.add_argument("kody", nargs="+", type=str, help="Kódy měřidel, např. E_CELKEM T_CELKEM W_CELKEM")
        parser.add_argument("--dry-run", action="store_true", help="Jen ukázat, co by se stalo")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        meters = list(Meter.objects.filter(code__in=options["kody"]))
        if not meters:
            self.stdout.write(self.style.WARNING(f"Žádné měřidlo s kódy {options['kody']} v databázi neexistuje."))
            return

        for meter in meters:
            self.stdout.write(self.style.WARNING(f"\n--- {meter} (#{meter.pk}, areál {meter.site}) ---"))

            items = ServicePoolItem.objects.filter(meter=meter)
            for item in items:
                self.stdout.write(f"  Položka '{item}' o něj přijde jako o Měřidlo (přejde na výpočet dle klíčů).")

            children = Meter.objects.filter(parent_meter=meter)
            for child in children:
                self.stdout.write(f"  Měřidlo '{child}' mělo {meter.code} jako Master měřidlo -> vynuluje se.")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n--dry-run: {len(meters)} měřidel by bylo smazáno, nic se neuložilo."))
            return

        Meter.objects.filter(parent_meter__in=meters).update(parent_meter=None)
        Meter.objects.filter(pk__in=[m.pk for m in meters]).delete()
        self.stdout.write(self.style.SUCCESS(f"\nSmazáno měřidel: {len(meters)}."))
