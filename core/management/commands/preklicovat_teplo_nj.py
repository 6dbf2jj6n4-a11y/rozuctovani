"""
Jednorazove preklicovani tepla NJ na model "spolecna vs individualni"
(konverzace s Danielem 2026-08-16).

Model: celkova spotreba tepla se nejdriv rozdeli mezi dve meridla podle
poctu radiatoru (T_SPOLECNA = radiatory ve spolecnych prostorach,
T_INDIVIDUALNI = radiatory v kancelarich), a teprve uvnitr kazde skupiny
se deli mezi klienty - u spolecne podle POCTU OSOB, u individualni podle
POCTU RADIATORU dane karty. Engine to umi bez zmeny: u polozky bez
hlavniho meridla se klice seskupi podle meridla, skupina dostane podil
= spotreba meridla / soucet, a uvnitr se deli vahou klicu
(billing/engine.py _consumption_shares).

Puvodni stav byl rozbity - dve polozky tepla, u kazde jina sada klicu,
temer kazdy klient dvakrat a vahy, ktere uz byly predpocitane podily.

VYCHOZI je jen NAHLED, zapisuje se az s --provest.

Pouziti:
  python manage.py preklicovat_teplo_nj
  python manage.py preklicovat_teplo_nj --provest
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import AllocationKey, ClientCard, Meter, ServicePoolItem, Site

# popis karty -> (radiatory v kancelarich, pocet osob, fakturovat)
# Podklad od Daniela 2026-08-16. "Karta CSE 2024 - 1" z jeho tabulky je
# v DB "Karta CSE 1 NJ" (popisy karet CALAMARI SE se uz jednou rozesly
# s Excelem - viz [[project_nj_elektro_submeter_engine_rework]]).
ROZPIS = {
    "Karta CSE 1 NJ": (1, 1, True),
    "Karta FSLCZ 2026 - 1": (0, 1, True),
    "Karta MAKER 2025 - 1": (2, 1, False),
    "Karta MVACTIVE 2025 - 1": (4, 2, True),
    "Karta ONEKLIMA 2026 - 1": (3, 5, True),
    "Karta EVUM 2026 - 1": (0, 2, True),
    "Karta AKTIVNOV 2026 - 1": (2, 2, True),
    "Karta DELPHIA 2026 - 1": (1, 1, False),
    "Karta MASTRCRANE 2026 - 1": (1, 1, False),
    "Karta GNES 2026 - 1": (1, 1, False),
    "Karta BURNTECH 2026 - 2": (3, 3, True),
    "Karta INNEXUM 2026 - 1": (2, 2, False),
}


class Command(BaseCommand):
    help = "Překlíčuje teplo NJ na T_SPOLECNA (osoby) + T_INDIVIDUALNI (radiátory)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--item", action="append",
            help="Název položky zásobníku (lze uvést víckrát). Výchozí: obě teplo NJ.",
        )
        parser.add_argument("--provest", action="store_true", help="Skutečně zapsat.")

    def handle(self, *args, **options):
        site = Site.objects.filter(name="NJ").first()
        if site is None:
            raise CommandError("Areál NJ nenalezen.")

        write = options["provest"]
        if not write:
            self.stdout.write(self.style.WARNING("NÁHLED - nic se nezapisuje (--provest).\n"))

        spolecna = Meter.objects.filter(site=site, code="T_SPOLECNA").first()
        individualni = Meter.objects.filter(site=site, code="T_INDIVIDUALNI").first()
        if spolecna is None or individualni is None:
            raise CommandError("Chybí měřidlo T_SPOLECNA nebo T_INDIVIDUALNI.")

        if options.get("item"):
            items = list(ServicePoolItem.objects.filter(site=site, name__in=options["item"]))
            chybi = set(options["item"]) - {i.name for i in items}
            if chybi:
                raise CommandError(f"Položky nenalezeny: {', '.join(sorted(chybi))}")
        else:
            items = list(ServicePoolItem.objects.filter(site=site, invoice_class="heat"))
        if not items:
            raise CommandError("Žádná položka tepla NJ.")

        karty = {}
        for popis, hodnoty in ROZPIS.items():
            card = ClientCard.objects.filter(description=popis).first()
            if card is None:
                raise CommandError(f"Karta '{popis}' nenalezena - oprav ROZPIS v příkazu.")
            karty[card] = hodnoty

        r_indiv = sum(v[0] for v in ROZPIS.values())
        r_spol = sum(v[1] for v in ROZPIS.values())
        self.stdout.write(
            f"Rozpis: {len(karty)} karet, součet radiátorů {r_indiv}, součet osob {r_spol}\n"
        )

        with transaction.atomic():
            for item in items:
                self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== {item.name} ==="))
                # Mazou se JEN klice karet z rozpisu. Karty, ktere v nem
                # nejsou (napr. budouci najemnici s platnosti od 9/2026),
                # si Daniel resi sam - nesmi o nastaveni prijit.
                vsechny = list(item.allocation_keys.select_related("client_card", "meter"))
                card_ids = {c.id for c in karty}
                stare = [k for k in vsechny if k.client_card_id in card_ids]
                cizi = [k for k in vsechny if k.client_card_id not in card_ids]

                self.stdout.write(f"  smazat starých klíčů: {len(stare)}")
                for k in sorted(stare, key=lambda x: str(x.client_card))[:60]:
                    self.stdout.write(
                        f"    − {str(k.client_card)[:34]:34} váha={k.value} "
                        f"měřidlo={k.meter.code if k.meter else '—'}"
                    )
                if cizi:
                    self.stdout.write(
                        f"  ponechat beze změny (mimo rozpis): {len(cizi)}"
                    )
                    for k in sorted(cizi, key=lambda x: str(x.client_card)):
                        self.stdout.write(
                            f"    = {str(k.client_card)[:34]:34} váha={k.value} "
                            f"měřidlo={k.meter.code if k.meter else '—'}"
                        )
                if write:
                    AllocationKey.objects.filter(
                        id__in=[k.id for k in stare]
                    ).delete()

                self.stdout.write(f"  založit nových klíčů: {len(karty) * 2}")
                for card, (radiatory, osoby, fakturovat) in sorted(
                    karty.items(), key=lambda kv: str(kv[0])
                ):
                    for meter, vaha, popis in (
                        (individualni, radiatory, "radiátorů"),
                        (spolecna, osoby, "osob"),
                    ):
                        self.stdout.write(
                            f"    + {str(card)[:32]:32} {meter.code:15} {vaha} {popis}"
                            f"{'' if fakturovat else '  (v paušálu)'}"
                        )
                        if write:
                            AllocationKey.objects.create(
                                service_item=item, client_card=card, meter=meter,
                                allocation_type=AllocationKey.AllocationType.WEIGHTED_COUNT,
                                value=Decimal(vaha), is_billed=fakturovat,
                            )
            if not write:
                transaction.set_rollback(True)

        if not write:
            self.stdout.write(self.style.WARNING("\nNic zapsáno nebylo (--provest)."))
        else:
            self.stdout.write(self.style.SUCCESS("\nHotovo. Přepočítej období a zkontroluj Detail výpočtu."))
        self.stdout.write(
            "\nPozor: rozdělení celku mezi obě části řídí ODEČET měřidel "
            "T_SPOLECNA / T_INDIVIDUALNI za dané období (počty radiátorů), "
            "ne součty vah tady."
        )
