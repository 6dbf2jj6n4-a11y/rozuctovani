"""
Diagnostika (jen cteni, nic nemeni): pro polozky bez hlavniho meridla
(service_item.meter=None) najde klice typu "Podle váhy" BEZ napojeneho
meridla - takove klice billing/engine.py._consumption_shares v tomhle
rezimu vyradi s varovanim "nema hlavni meridlo - neni vuci cemu urcit
jejich podil" (viz konverzace s Danielem, FM 07/2026).

Pouziti:
  python manage.py diag_klice_bez_meridla --period=07/2026 --item="hlavní odběr elektro FM"
"""
from django.core.management.base import BaseCommand, CommandError

from billing.engine import ABSOLUTE_AMOUNT_TYPES, _meter_provides_consumption
from core.models import Period, ServicePoolItem


class Command(BaseCommand):
    help = 'Najde karty s klíčem "Podle váhy" bez měřidla u položky bez hlavního měřidla.'

    def add_arguments(self, parser):
        parser.add_argument("--period", required=True, help="MM/RRRR, např. 07/2026")
        parser.add_argument("--item", required=True)

    def handle(self, *args, **options):
        month_str, year_str = options["period"].split("/")
        period = Period.objects.filter(year=int(year_str), month=int(month_str)).first()
        if period is None:
            raise CommandError(f"Období {options['period']} nenalezeno.")

        item = ServicePoolItem.objects.filter(name__icontains=options["item"]).first()
        if item is None:
            raise CommandError(f'Položka obsahující {options["item"]!r} nenalezena.')

        if item.meter:
            self.stdout.write(self.style.SUCCESS(
                f"{item} má hlavní měřidlo ({item.meter}) - tenhle problém se jí netýká."
            ))
            return

        valid_keys = [
            k for k in item.allocation_keys.select_related("client_card__client", "meter")
            if k.is_valid_for_period(period) and k.allocation_type not in ABSOLUTE_AMOUNT_TYPES
        ]
        has_meter_keys = any(
            k.meter_id is not None and _meter_provides_consumption(k.meter) for k in valid_keys
        )
        if not has_meter_keys:
            self.stdout.write(self.style.WARNING(
                f"{item}: žádný klíč nemá reálné měřidlo - položka se počítá čistě podle váhy "
                f"(žádný z klíčů tímto problémem netrpí)."
            ))
            return

        without_meter = [k for k in valid_keys if k.meter_id is None]
        if not without_meter:
            self.stdout.write(self.style.SUCCESS(f"{item}: všechny platné klíče mají měřidlo."))
            return

        self.stdout.write(self.style.ERROR(
            f"{item} / {period}: {len(without_meter)} klíč(ů) BEZ měřidla, budou vynechány:"
        ))
        for key in without_meter:
            self.stdout.write(
                f"  {key.client_card.client.name} ({key.client_card}): "
                f"{key.get_allocation_type_display()} hodnota={key.value}"
            )
