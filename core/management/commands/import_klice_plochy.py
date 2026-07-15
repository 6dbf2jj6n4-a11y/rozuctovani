"""
Import klicu-ploch z Excel souboru Klice_Plochy.xlsx.
Pro kazdy radek:
1. Najde ClientCard podle PopisKarty
2. Najde Unit podle IDPLOCHY
3. Vytvori nebo aktualizuje CardUnit s vymerou a sazbou

Pouziti:
  python manage.py import_klice_plochy cesta/k/souboru.xlsx --site FM
"""
import openpyxl
from decimal import Decimal
from django.core.management.base import BaseCommand
from core.models import Site, Unit, ClientCard, CardUnit


class Command(BaseCommand):
    help = "Importuje klice-plochy (CardUnit) z Excel souboru"

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path", type=str)
        parser.add_argument("--site", type=str, default="FM")

    def handle(self, *args, **options):
        site = Site.objects.filter(name__icontains=options["site"]).first()
        if not site:
            self.stdout.write(self.style.ERROR(f"Areál '{options['site']}' nenalezen."))
            return

        wb = openpyxl.load_workbook(options["xlsx_path"], read_only=True, data_only=True)
        ws = wb.active
        headers = [str(c.value).strip() if c.value else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]

        created = 0
        updated = 0
        skipped = 0

        for row in ws.iter_rows(min_row=2, values_only=True):
            data = dict(zip(headers, row))

            card_desc = str(data.get("PopisKarty") or "").strip()
            unit_code = str(data.get("IDPLOCHY") or "").strip()
            pronajato = data.get("PronajatoM")
            sazba = data.get("SazbaKcMRok")
            aktivni = str(data.get("Aktivni") or "").strip().lower()

            if not card_desc or not unit_code or aktivni != "zapnuto":
                skipped += 1
                continue

            card = ClientCard.objects.filter(description=card_desc, is_active=True).first()
            if not card:
                self.stdout.write(f"  Karta nenalezena: {card_desc}")
                skipped += 1
                continue

            unit = Unit.objects.filter(code=unit_code, site=site).first()
            if not unit:
                # Zkusime hledat bez arealu (pro plochy bez site)
                unit = Unit.objects.filter(code=unit_code).first()
            if not unit:
                self.stdout.write(f"  Plocha nenalezena: {unit_code}")
                skipped += 1
                continue

            area_override = Decimal(str(pronajato)) if pronajato else None
            rate = Decimal(str(sazba)) if sazba and float(sazba) > 0 else None

            card_unit, was_created = CardUnit.objects.update_or_create(
                card=card,
                unit=unit,
                defaults={
                    "area_m2_override": area_override,
                    "rate_per_m2": rate,
                },
            )

            if was_created:
                created += 1
                self.stdout.write(f"  + {card_desc} / {unit_code}: {area_override} m² @ {rate} Kč")
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nHotovo: {created} vytvořeno, {updated} aktualizováno, {skipped} přeskočeno."
        ))
