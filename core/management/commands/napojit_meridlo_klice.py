"""
Jednorazova oprava: napoji zadane meridlo (podle kodu) na vsechny klice
typu "Podle váhy" dane polozky, ktere zatim zadne meridlo nemaji - typicky
kvuli popisku "Co je vahou" (Meter.weight_unit_label), viz konverzace
s Danielem (napr. "Úklidové služby budova A (FM)" -> meridlo EKLID_FM,
vaha = pocet osob). NEMENI hodnotu klice (value), jen pripoji meridlo.

BEZ --provest jen VYPISE, co by zmenil. S --provest ulozi.

Pouziti:
  python manage.py napojit_meridlo_klice --item="Úklidové služby budova A" --meter-code=EKLID_FM
  python manage.py napojit_meridlo_klice --item="Úklidové služby budova A" --meter-code=EKLID_FM --provest
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import AllocationKey, Meter, ServicePoolItem


class Command(BaseCommand):
    help = 'Napojí zadané měřidlo na klíče "Podle váhy" dané položky, které zatím žádné měřidlo nemají.'

    def add_arguments(self, parser):
        parser.add_argument("--item", required=True)
        parser.add_argument("--meter-code", required=True)
        parser.add_argument("--provest", action="store_true", help="Skutečně uložit (jinak jen náhled).")

    def handle(self, *args, **options):
        item = ServicePoolItem.objects.filter(name__icontains=options["item"]).first()
        if item is None:
            raise CommandError(f'Položka obsahující {options["item"]!r} nenalezena.')

        meter = Meter.objects.filter(code__iexact=options["meter_code"]).first()
        if meter is None:
            candidates = Meter.objects.filter(site=item.site, code__icontains=options["meter_code"][:4])
            names = ", ".join(f"{m.code!r} ({m})" for m in candidates) or "(nic podobného)"
            raise CommandError(f'Měřidlo s kódem {options["meter_code"]!r} nenalezeno. Podobné: {names}')

        self.stdout.write(f"Položka: {item}")
        self.stdout.write(f"Měřidlo: {meter} (kód={meter.code}, Co je váhou={meter.weight_unit_label or '(nevyplněno!)'})")

        keys = AllocationKey.objects.filter(
            service_item=item,
            allocation_type=AllocationKey.AllocationType.WEIGHTED_COUNT,
            meter__isnull=True,
        ).select_related("client_card__client")

        if not keys:
            self.stdout.write(self.style.SUCCESS("\nŽádné klíče bez měřidla nenalezeny - nic k opravě."))
            return

        self.stdout.write(self.style.WARNING(f"\nNalezeno {keys.count()} klíčů bez měřidla:"))
        for key in keys:
            self.stdout.write(f"  {key.client_card.client.name} ({key.client_card}): hodnota={key.value}")

        if options["provest"]:
            count = keys.update(meter=meter)
            self.stdout.write(self.style.SUCCESS(f"\nNapojeno {count} klíčů na měřidlo {meter}."))
        else:
            self.stdout.write(self.style.WARNING("\nToto byl jen náhled. Pro uložení spusť s --provest."))
