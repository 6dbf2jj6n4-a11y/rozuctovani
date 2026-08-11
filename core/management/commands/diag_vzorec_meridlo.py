"""
Diagnostika (jen cteni): pro virtualni meridlo se Vzorcem (napr. E_SPOL)
ukaze rozpad vypoctu po jednotlivych clenech vzorce - u kazdeho clenu
surovy odecet, odectene prime deti (Meter.children) a vyslednou "vlastni"
hodnotu, ktera do vzorce po oprave 2026-08-13 skutecne vstupuje
(_consumption_net_of_children), plus celkovy soucet = spotreba
virtualniho meridla za obdobi.

Slouzi k overeni, ze do E_SPOL vstupuje zbytek master meridla (napr.
E_A7 ~473), ne jeho surovy odecet vc. samostatne uctovanych najemniku
(1214).

Pouziti:
  python manage.py diag_vzorec_meridlo --site FM --period=07/2026 --kod E_SPOL
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from core.models import Meter, Period, Site


class Command(BaseCommand):
    help = "Rozpad vypoctu virtuálního měřidla (Vzorec) po členech - surová vs. očištěná hodnota."

    def add_arguments(self, parser):
        parser.add_argument("--site", required=True)
        parser.add_argument("--period", required=True, help="MM/RRRR")
        parser.add_argument("--kod", required=True, help="kód virtuálního měřidla (např. E_SPOL)")

    def handle(self, *args, **options):
        site = Site.objects.filter(name__icontains=options["site"]).first()
        if not site:
            raise CommandError(f"Areál '{options['site']}' nenalezen.")

        month_str, year_str = options["period"].split("/")
        period = Period.objects.filter(year=int(year_str), month=int(month_str)).first()
        if period is None:
            raise CommandError(f"Období {options['period']} nenalezeno.")

        meter = Meter.objects.filter(site=site, code=options["kod"]).first()
        if meter is None:
            raise CommandError(f"Měřidlo '{options['kod']}' v areálu {site} nenalezeno.")
        if not meter.is_virtual:
            raise CommandError(f"Měřidlo {meter} není virtuální (nemá Vzorec) - není co rozpadat.")

        self.stdout.write(self.style.WARNING(f"\n=== {meter.code} : Vzorec = '{meter.formula}' ({period}) ==="))

        total = Decimal("0")
        for component, sign in meter._formula_tokens():
            sign_label = "+" if sign > 0 else "−"
            if component.is_virtual:
                net = component._consumption_net_of_children(period)
                self.stdout.write(
                    f"  {sign_label} {component.code:<12} (virtuální) → {net}"
                )
            else:
                raw = component.consumption_for(period)
                children = list(component.children.all())
                net = component._consumption_net_of_children(period)
                self.stdout.write(f"  {sign_label} {component.code:<12} surový odečet = {raw}")
                for child in children:
                    cc = child.consumption_for(period)
                    self.stdout.write(f"        − dítě {child.code:<12} = {cc}")
                marker = "" if not children else self.style.SUCCESS("  ← očištěno o děti")
                self.stdout.write(f"        = vlastní (vstupuje do vzorce) = {net}{marker}")
            if net is not None:
                total += sign * net

        self.stdout.write(self.style.MIGRATE_HEADING(f"\n  SPOTŘEBA {meter.code} za {period} = {total}"))
        self.stdout.write(
            f"  (pro srovnání: consumption_for() = {meter.consumption_for(period)})"
        )
