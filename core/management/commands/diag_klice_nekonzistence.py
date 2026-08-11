"""
Diagnostika (jen čtení, nic nemění): plošný audit AllocationKey napříč
celou DB, hledá stejný vzor nekonzistencí, jaký se ručně našel u karet
Mgr. Lucie Halamová a NORVITT ENGINEERING na položce "hlavní odběr
elektro FM" (viz konverzace s Danielem, 2026-08-09/10):

  A) Duplicitní klíče - stejná karta + položka + typ + hodnota (+ měřidlo)
     se opakuje víckrát (typicky import omylem přidal řádek navíc).
  B) Klíče napojené na "prázdné" virtuální měřidlo - meter.is_virtual=True
     a meter.formula je prázdný string, takže měřidlo fakticky nic
     nepočítá (odkaz je inertní, ale u typů, které meter vůbec nepoužívají
     - area_price, weighted_count, fixed_amount - je to samo o sobě
     podezřelé, protože k čemu je pak měřidlo navázané).
  C) Typ klíče, který se liší od většiny ostatních karet na téže položce
     zásobníku (ServicePoolItem) - když 4 karty mají "submeter" a jedna
     "area_price" na stejné položce, ta jedna je podezřelá.

Účel: zjistit ROZSAH problému před jakoukoliv opravou. Nic nezapisuje.

Použití:
  python manage.py diag_klice_nekonzistence
  python manage.py diag_klice_nekonzistence --site FM
  python manage.py diag_klice_nekonzistence --jen-aktivni-karty
"""
from collections import defaultdict

from django.core.management.base import BaseCommand

from core.models import AllocationKey


class Command(BaseCommand):
    help = "Plošný audit AllocationKey: duplicity, klíče na prázdných virtuálních měřidlech, typ odlišný od peerů na položce."

    def add_arguments(self, parser):
        parser.add_argument("--site", default=None, help="Filtrovat podle názvu areálu (např. FM, NJ) - substring match.")
        parser.add_argument(
            "--jen-aktivni-karty", action="store_true",
            help="Zahrnout jen klíče karet s client_card.is_active=True.",
        )

    def handle(self, *args, **options):
        qs = AllocationKey.objects.select_related(
            "client_card__client", "service_item__site", "meter"
        )
        if options["site"]:
            qs = qs.filter(service_item__site__name__icontains=options["site"])
        if options["jen_aktivni_karty"]:
            qs = qs.filter(client_card__is_active=True)

        keys = list(qs.order_by("service_item__site__name", "service_item__name", "client_card__client__name"))
        self.stdout.write(self.style.WARNING(f"Celkem klíčů v rozsahu: {len(keys)}\n"))

        self._audit_duplicity(keys)
        self._audit_prazdna_virtualni_meridla(keys)
        self._audit_typ_odlisny_od_peeru(keys)

    # A) duplicitní klíče --------------------------------------------------
    def _audit_duplicity(self, keys):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== A) Duplicitní klíče (karta + položka + typ + hodnota + měřidlo) ==="))
        groups = defaultdict(list)
        for k in keys:
            sig = (k.client_card_id, k.service_item_id, k.allocation_type, k.value, k.meter_id)
            groups[sig].append(k)

        found = 0
        for sig, rows in groups.items():
            if len(rows) < 2:
                continue
            found += 1
            k0 = rows[0]
            self.stdout.write(
                f"\nKarta #{k0.client_card_id} '{k0.client_card.client}' | "
                f"položka '{k0.service_item.name}' ({k0.service_item.site}) | "
                f"{len(rows)}x typ={k0.allocation_type} hodnota={k0.value} "
                f"měřidlo={k0.meter.code if k0.meter else '-'}"
            )
            for r in rows:
                self.stdout.write(f"    klíč #{r.pk}")

        if not found:
            self.stdout.write(self.style.SUCCESS("  Žádné duplicity nenalezeny."))
        else:
            self.stdout.write(self.style.ERROR(f"\n  Celkem {found} skupin duplicit."))

    # B) klíče na prázdném virtuálním měřidle -------------------------------
    def _audit_prazdna_virtualni_meridla(self, keys):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== B) Klíče napojené na prázdné virtuální měřidlo (is_virtual=True, formula='') ==="))
        bad = [
            k for k in keys
            if k.meter_id and k.meter.is_virtual and not k.meter.formula.strip()
        ]
        if not bad:
            self.stdout.write(self.style.SUCCESS("  Žádné takové klíče nenalezeny."))
            return

        for k in bad:
            no_readings = not k.meter.readings.exists()
            self.stdout.write(
                f"  klíč #{k.pk} | karta #{k.client_card_id} '{k.client_card.client}' | "
                f"položka '{k.service_item.name}' ({k.service_item.site}) | "
                f"typ={k.allocation_type} hodnota={k.value} | "
                f"měřidlo={k.meter.code} (formula='', odečty={'0' if no_readings else 'MÁ odečty!'})"
            )
        self.stdout.write(self.style.ERROR(f"\n  Celkem {len(bad)} klíčů na prázdném virtuálním měřidle."))

    # C) typ klíče odlišný od peerů na stejné položce -----------------------
    def _audit_typ_odlisny_od_peeru(self, keys):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== C) Typ klíče odlišný od většiny peerů na téže položce ==="))
        by_item = defaultdict(list)
        for k in keys:
            by_item[k.service_item_id].append(k)

        found_items = 0
        for item_id, rows in by_item.items():
            type_counts = defaultdict(int)
            for r in rows:
                type_counts[r.allocation_type] += 1
            if len(type_counts) < 2:
                continue
            found_items += 1
            majority_type = max(type_counts, key=type_counts.get)
            item = rows[0].service_item
            self.stdout.write(
                f"\nPoložka '{item.name}' ({item.site}) - rozložení typů: "
                + ", ".join(f"{t}={n}" for t, n in sorted(type_counts.items(), key=lambda x: -x[1]))
            )
            for r in rows:
                if r.allocation_type != majority_type:
                    self.stdout.write(
                        f"    ODLIŠNÝ: klíč #{r.pk} karta #{r.client_card_id} '{r.client_card.client}' | "
                        f"typ={r.allocation_type} (většina má {majority_type}) | "
                        f"hodnota={r.value} měřidlo={r.meter.code if r.meter else '-'}"
                    )

        if not found_items:
            self.stdout.write(self.style.SUCCESS("  Žádné položky se smíšenými typy klíčů nenalezeny."))
        else:
            self.stdout.write(self.style.ERROR(f"\n  Celkem {found_items} položek se smíšenými typy klíčů."))
