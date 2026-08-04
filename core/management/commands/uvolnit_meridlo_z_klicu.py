"""
Opak napojit_meridlo_klice.py: pro dane meridlo, ktere u teto polozky
slouzilo jen jako nosic popisku "Co je vahou" (zadne skutecne mereni),
presune jeho weight_unit_label na ServicePoolItem.weight_unit_label a
odpoji ho od vsech klicu polozky (meter=None) - viz konverzace s
Danielem, zjednoduseni modelu (2026-08).

POZOR: pouzij jen u meridel, ktera na teto polozce nemaji zadny skutecny
ucel (zadne odecty, neni virtualni se vzorcem) - jinak by odpojenim
klicu prisel vypocet o realny zdroj spotreby. U meridel sdilenych s
JINYMI polozkami (napr. T_SPOLECNA pouzite na vic polozkach teplo NJ)
spusti zvlast pro kazdou polozku - samotne meridlo (a jeho popisek) se
nemaze, jen odpojuje z konkretnich klicu.

BEZ --provest jen VYPISE, co by zmenil. S --provest ulozi.

Pouziti:
  python manage.py uvolnit_meridlo_z_klicu --item="Úklidové služby budova A" --meter-code=EKLID_FM
  python manage.py uvolnit_meridlo_z_klicu --item="Úklidové služby budova A" --meter-code=EKLID_FM --provest
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import AllocationKey, Meter, ServicePoolItem


class Command(BaseCommand):
    help = 'Přesune "Co je váhou" z měřidla na položku a odpojí ho od jejích klíčů.'

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
            raise CommandError(f'Měřidlo s kódem {options["meter_code"]!r} nenalezeno.')

        keys = AllocationKey.objects.filter(service_item=item, meter=meter)
        if not keys:
            self.stdout.write(self.style.SUCCESS("Žádné klíče této položky na tomto měřidle - nic k odpojení."))
            return

        self.stdout.write(f"Položka: {item}")
        self.stdout.write(f"Měřidlo: {meter} - Co je váhou: {meter.weight_unit_label or '(prázdné)'}")
        if item.weight_unit_label and item.weight_unit_label != meter.weight_unit_label:
            self.stdout.write(self.style.WARNING(
                f'POZOR: položka už má jiný popisek "{item.weight_unit_label}" - přepíše se na "{meter.weight_unit_label}".'
            ))

        self.stdout.write(self.style.WARNING(f"\nOdpojí se {keys.count()} klíčů od měřidla {meter}:"))
        for key in keys.select_related("client_card__client"):
            self.stdout.write(f"  {key.client_card.client.name} ({key.client_card}): hodnota={key.value}")

        if options["provest"]:
            item.weight_unit_label = meter.weight_unit_label
            item.save(update_fields=["weight_unit_label"])
            count = keys.update(meter=None)
            self.stdout.write(self.style.SUCCESS(
                f"\nPopisek přesunut na položku, {count} klíčů odpojeno od měřidla {meter}."
            ))
        else:
            self.stdout.write(self.style.WARNING("\nToto byl jen náhled. Pro uložení spusť s --provest."))
