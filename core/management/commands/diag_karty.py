"""
Diagnostický (jen čtecí) výpis karet klienta - plochy, sazby, platnost.
Použití:
  python manage.py diag_karty "Aktiv Novostav"
  python manage.py diag_karty "LOGICV"
"""
from django.core.management.base import BaseCommand

from core.models import Client, ClientCard


class Command(BaseCommand):
    help = "Vypíše karty (a jejich plochy/sazby) klientů, jejichž jméno nebo popis karty odpovídá zadanému textu."

    def add_arguments(self, parser):
        parser.add_argument("text", type=str, help="Část jména klienta nebo popisu karty")

    def handle(self, *args, **options):
        text = options["text"]

        clients = Client.objects.filter(name__icontains=text)
        cards = ClientCard.objects.filter(description__icontains=text)

        card_ids = set(cards.values_list("id", flat=True))
        for c in clients:
            card_ids.update(c.cards.values_list("id", flat=True))

        if not card_ids:
            self.stdout.write(self.style.WARNING(f"Nic nenalezeno pro '{text}'."))
            return

        for card in ClientCard.objects.filter(id__in=card_ids).select_related("client").order_by("client__name", "valid_from"):
            self.stdout.write(
                f"\nKarta #{card.pk}: '{card.description}' | klient: {card.client} | "
                f"aktivní: {card.is_active} | platnost: {card.valid_from} - {card.valid_to or '(neurčito)'}"
            )
            units = list(card.card_units.select_related("unit__site"))
            if not units:
                self.stdout.write(self.style.WARNING("  ŽÁDNÉ plochy (CardUnit) na této kartě."))
                continue
            for cu in units:
                self.stdout.write(
                    f"  {cu.unit} | výměra: {cu.area_m2} m² (override: {cu.area_m2_override}) | "
                    f"sazba: {cu.rate_per_m2} Kč/m²/rok | nájemné/měsíc: {cu.monthly_rent}"
                )
