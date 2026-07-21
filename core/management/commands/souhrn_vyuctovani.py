"""
Vypise soucet Vyuctovanych polozek (BillingLine) po polozkach zasobniku
pro dane obdobi/areal - pro rucni porovnani s referencnimi cisly
(napr. radek "Fakturace celkem Kc" v Spotreby_2026_FM.xlsx).

Pouziti:
  python manage.py souhrn_vyuctovani 06/2026 --site FM
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import BillingLine, Period, Site


class Command(BaseCommand):
    help = "Vypíše součet Vyúčtovaných položek po položkách zásobníku pro dané období/areál."

    def add_arguments(self, parser):
        parser.add_argument("period", type=str, help="MM/YYYY, např. 06/2026")
        parser.add_argument("--site", type=str, required=True)

    def handle(self, *args, **options):
        try:
            month_str, year_str = options["period"].split("/")
            month, year = int(month_str), int(year_str)
        except ValueError:
            raise CommandError("Období zadej ve formátu MM/YYYY, např. 06/2026")

        period = Period.objects.filter(year=year, month=month).first()
        if not period:
            raise CommandError(f"Období {options['period']} neexistuje.")

        site = Site.objects.filter(name__icontains=options["site"]).first()
        if not site:
            raise CommandError(f"Areál '{options['site']}' nenalezen.")

        lines = BillingLine.objects.filter(
            period=period, service_item__site=site
        ).select_related("service_item")

        totals = {}
        counts = {}
        for line in lines:
            key = line.service_item.name
            totals[key] = totals.get(key, 0) + line.amount
            counts[key] = counts.get(key, 0) + 1

        if not totals:
            self.stdout.write(self.style.WARNING(
                f"Žádné Vyúčtované položky pro {period} / {site} - nejdřív spusť přepočet "
                f"(admin akce 'Spočítat rozúčtování za vybraná období – jen {site}')."
            ))
            return

        self.stdout.write(f"Souhrn Vyúčtovaných položek za {period} / {site}:\n")
        grand_total = 0
        for name in sorted(totals):
            total = totals[name]
            self.stdout.write(f"  {name} ({counts[name]}×): {total:,.2f} Kč".replace(",", " "))
            grand_total += total
        self.stdout.write(self.style.SUCCESS(
            f"\nCelkem ({site}, {period}): {grand_total:,.2f} Kč".replace(",", " ")
        ))
