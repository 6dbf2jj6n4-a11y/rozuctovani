"""
Diagnostika (jen cteni): kolik AllocationKey radku v DB pouziva ktery
allocation_type - podklad pro rozhodnuti, ktere typy jde bezpecne zrusit
(percent/area_ratio/equal_split) a ktere je potreba pred zrusenim
prevest na "weighted_count" (person_count).

Pouziti:
  python manage.py diag_typy_pouziti
"""
from django.core.management.base import BaseCommand
from django.db.models import Count

from core.models import AllocationKey


class Command(BaseCommand):
    help = "Vypíše počet klíčů podle allocation_type (celkem a po položkách u person_count)."

    def handle(self, *args, **options):
        counts = (
            AllocationKey.objects.values("allocation_type")
            .annotate(n=Count("id"))
            .order_by("-n")
        )
        labels = dict(AllocationKey.AllocationType.choices)
        self.stdout.write(self.style.WARNING("=== Počet klíčů podle typu (celá DB) ==="))
        for row in counts:
            t = row["allocation_type"]
            self.stdout.write(f"  {t} ({labels.get(t, '?')}): {row['n']}")

        self.stdout.write(self.style.WARNING("\n=== Kde konkrétně se používá 'person_count' (podle položky) ==="))
        person_keys = (
            AllocationKey.objects.filter(allocation_type="person_count")
            .values("service_item__site__name", "service_item__name")
            .annotate(n=Count("id"))
            .order_by("service_item__site__name", "service_item__name")
        )
        for row in person_keys:
            self.stdout.write(f"  [{row['service_item__site__name']}] {row['service_item__name']}: {row['n']} klíčů")

        for t in ("percent", "area_ratio", "equal_split"):
            rows = AllocationKey.objects.filter(allocation_type=t).select_related(
                "client_card__client", "service_item"
            )[:20]
            if rows:
                self.stdout.write(self.style.WARNING(f"\n=== Ukázka klíčů typu '{t}' (max 20) ==="))
                for key in rows:
                    self.stdout.write(f"  {key.client_card.client.name} / {key.service_item.name}: hodnota={key.value}")
