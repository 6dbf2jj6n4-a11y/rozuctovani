"""
Diagnostika (jen cteni): pro FM ukaze, jake ServicePoolItem existuji pro
tridy ELEKTRO/VODA/TEPLO a jestli maji nastavene item.meter - a pro par
konkretnich kodu meridel z Klice_*.xlsx (ktere import_klice_*.py nemohl
napojit) ukaze cely retezec parent_meter az ke koreni, aby bylo videt,
proc se nenasel odpovidajici ServicePoolItem.

Pouziti:
  python manage.py diag_fm_meridla_polozky
"""
from django.core.management.base import BaseCommand

from core.models import Meter, ServicePoolItem, Site

SAMPLE_CODES = {
    "elektro": ["E_SPOL", "E_PAUS", "E_A1", "E_N2", "668NT"],
    "voda": ["W_TUV", "W_A1", "W_SRAZK"],
    "teplo": ["T_TUV", "T_A1S", "T_PAUS"],
}


class Command(BaseCommand):
    help = "Ukáže ServicePoolItem.meter pro FM elektro/voda/teplo a hierarchii pro pár vzorových kódů."

    def handle(self, *args, **options):
        site = Site.objects.filter(name__icontains="FM").first()
        if not site:
            self.stdout.write(self.style.ERROR("Areál FM nenalezen."))
            return

        self.stdout.write(self.style.WARNING("=== ServicePoolItem (ELEKTRO/VODA/TEPLO) na FM ==="))
        items = ServicePoolItem.objects.filter(
            site=site, invoice_class__in=["elektro", "voda", "teplo"]
        ).select_related("meter")
        for item in items:
            self.stdout.write(f"  {item.name!r} (třída={item.invoice_class}) -> meter={item.meter}")

        for meter_type, codes in SAMPLE_CODES.items():
            self.stdout.write(self.style.WARNING(f"\n=== Hierarchie vzorových měřidel ({meter_type}) ==="))
            for code in codes:
                meter = Meter.objects.filter(site=site, code=code).first()
                if meter is None:
                    self.stdout.write(f"  {code}: měřidlo NENALEZENO v DB")
                    continue
                chain = [meter]
                node = meter
                while node.parent_meter:
                    node = node.parent_meter
                    chain.append(node)
                chain_str = " -> ".join(f"{m.code}(id={m.id})" for m in chain)
                root = chain[-1]
                item_direct = ServicePoolItem.objects.filter(meter=meter, site=site).first()
                item_root = ServicePoolItem.objects.filter(meter=root, site=site).first()
                self.stdout.write(
                    f"  {code}: řetězec={chain_str} | "
                    f"item_na_přímém_měřidle={item_direct} | item_na_kořeni={item_root}"
                )
