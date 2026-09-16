"""
NJ: klic na "revize hasicich pristroju" pro kazdou Kartu.

Daniel 2026-09-16: polozku mela jedina Karta (CALAMARI, a jeste s vahou
223 opsanou z vymery, coz s revizemi nesouvisi). Spravedlive se to deli
podle POCTU HASICICH PRISTROJU - ty se doplni rucne, tenhle prikaz jen
zalozi radky, kam je zapsat.

Klice vznikaji s PRAZDNOU vahou (value = None), takze dokud se pocty
nedoplni, nikdo nic neplati a vypocet na to upozorni sam. Priznaky
Fakturovat / Odecist z celkoveho nakladu se prebiraji z klice na uklid
spolecnych prostor te same Karty - je to stejny druh arealove sluzby,
takze pausalni klienti zustanou pausalni.

Karty, ktere skoncily pred 08/2026, se vynechavaji - drivejsi obdobi uz
jsou vyfakturovana a nemaji se menit.

Prikaz je OPAKOVATELNY - druhe spusteni uz nema co zalozit a existujici
vahy nikdy neprepisuje.

Pouziti:
  python manage.py klice_revize_hasicich_nj            # jen ukaze
  python manage.py klice_revize_hasicich_nj --provest  # zapise
"""
import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import AllocationKey, ServicePoolItem, Site

OD_OBDOBI = datetime.date(2026, 8, 1)


class Command(BaseCommand):
    help = "NJ: založí klíč „revize hasících přístrojů“ všem kartám (váha = počet přístrojů, doplní se ručně)."

    def add_arguments(self, parser):
        parser.add_argument("--provest", action="store_true", help="Skutečně zapsat.")

    def handle(self, *args, **volby):
        zapsat = volby["provest"]
        site = Site.objects.filter(name="NJ").first()
        if site is None:
            raise CommandError("Areál NJ neexistuje.")
        revize = ServicePoolItem.objects.filter(site=site, name="revize hasících přístrojů").first()
        uklid = ServicePoolItem.objects.filter(
            site=site, name="úklidové služby společných prostor NJ").first()
        if revize is None or uklid is None:
            raise CommandError("Položky „revize hasících přístrojů“ / „úklidové služby…“ neexistují.")

        if not zapsat:
            self.stdout.write(self.style.WARNING("NÁHLED - nic se nezapisuje, spusť s --provest.\n"))

        uz_ma = set(AllocationKey.objects.filter(service_item=revize).values_list("client_card_id", flat=True))
        zalozit, upravit = [], []

        for vzor in AllocationKey.objects.filter(
            service_item=uklid
        ).select_related("client_card__client"):
            karta = vzor.client_card
            if karta.valid_to and karta.valid_to < OD_OBDOBI:
                continue
            if karta.id in uz_ma:
                continue
            zalozit.append(vzor)

        # CALAMARI ma vahu opsanou z vymery - s pocty hasicich pristroju
        # nema nic spolecneho, at se doplni stejne jako ostatnim.
        for klic in AllocationKey.objects.filter(
            service_item=revize
        ).select_related("client_card__client"):
            if klic.client_card.valid_to and klic.client_card.valid_to < OD_OBDOBI:
                continue
            if klic.value is not None or klic.weight_source:
                upravit.append(klic)

        typ = AllocationKey.AllocationType.WEIGHTED_COUNT
        self.stdout.write(self.style.MIGRATE_HEADING(f"Založit klíče ({len(zalozit)}):"))
        for vzor in sorted(zalozit, key=lambda v: str(v.client_card)):
            self.stdout.write(
                f"   karta #{vzor.client_card_id:<4} {str(vzor.client_card)[:38]:38} "
                f"váha prázdná, fakturovat={'ANO' if vzor.is_billed else 'ne'}, "
                f"odečíst={'ANO' if vzor.deduct_from_pool else 'ne'}"
            )
        if upravit:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\nVyprázdnit váhu opsanou odjinud ({len(upravit)}):"))
            for klic in upravit:
                self.stdout.write(
                    f"   klíč #{klic.pk:<5} karta #{klic.client_card_id:<4} "
                    f"{str(klic.client_card)[:34]:34} {klic.value} / {klic.weight_source or '-'} -> prázdná"
                )
        if revize.default_allocation_type != typ:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\nVýchozí typ položky: {revize.default_allocation_type} -> {typ}"))

        if not zapsat:
            return

        with transaction.atomic():
            AllocationKey.objects.bulk_create([
                AllocationKey(
                    client_card=vzor.client_card,
                    service_item=revize,
                    allocation_type=typ,
                    value=None,
                    is_billed=vzor.is_billed,
                    deduct_from_pool=vzor.deduct_from_pool,
                )
                for vzor in zalozit
            ])
            for klic in upravit:
                klic.allocation_type = typ
                klic.value = None
                klic.weight_source = ""
                klic.save(update_fields=["allocation_type", "value", "weight_source"])
            if revize.default_allocation_type != typ:
                revize.default_allocation_type = typ
                revize.save(update_fields=["default_allocation_type"])

        self.stdout.write(self.style.SUCCESS(
            f"\nHotovo: založeno {len(zalozit)}, upraveno {len(upravit)}. "
            f"Doplň počty hasících přístrojů a přepočítej období."
        ))
