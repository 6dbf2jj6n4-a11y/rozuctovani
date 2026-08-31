"""
Polozky zasobniku sluzeb a Klice pro areal DV (Dvorakova 1346/13).

DV melo meridla i karty, ale zadnou polozku zasobniku, takze nebylo co
rozuctovat. Tenhle prikaz doplni pet polozek podle rozpisu predepsanych
plateb (Voda, Teplo, Spolecna elektrina, Vytah, Uklid) plus preuctovani
elektriny nebytovych prostor, a ke kazde zalozi Klice na aktivni Karty.

Zpusob deleni podle Daniela 2026-08-25:
  * voda a teplo   - podle podruznych meridel (kazdy prostor ma svoje),
  * spolecna elektrina a uklid - ROVNYM DILEM na jednotku,
  * vytah          - rovnym dilem, ale jen mezi devet jednotek: D1 a E1
                     jsou kancelare v prizemi a vytah nepotrebuji,
  * elektrina D1/E1/H2 - preuctuje se podle vlastnich elektromeru
                     (byty vlastni elektromer nemaji, maji smlouvu primo
                     s dodavatelem).

"Rovnym dilem" se zapisuje jako Klic typu Podle vahy s vahou 1 u kazde
karty - system vahy normalizuje na 100 %, takze stejna vaha = stejny dil.
Prazdny prostor kartu nema, takze klic nedostane a jeho podil nesou
ostatni; az se pronajme, klic se doplni (D1 je dnes volne).

VYCHOZI je jen NAHLED, zapisuje se az s --provest. Opakovane spusteni uz
nic nemeni (co existuje, se preskoci).

Pouziti:
  python manage.py bootstrap_zasobnik_dv
  python manage.py bootstrap_zasobnik_dv --provest
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from core.models import AllocationKey, CardUnit, Meter, ServicePoolItem, Site

BEZ_VYTAHU = ("D1", "E1")          # kancelare v prizemi
S_ELEKTROMEREM = ("D1", "E1", "H2")  # nebytove prostory, ktere elektrinu meri

# (nazev, trida, kod meridla polozky, zpusob, popis vahy)
POLOZKY = [
    ("hlavní odběr voda DV", "voda", "W_DV_CELKEM", "submeter", ""),
    ("hlavní odběr teplo DV", "teplo", None, "submeter", ""),
    ("společná elektřina DV", "elektro", "E_SPOL", "rovnym_dilem", "jednotek"),
    ("výtah DV", "elektro", "E_VYTAH", "rovnym_dilem_bez_prizemi", "jednotek"),
    ("úklid společných prostor DV", "ostatni", None, "rovnym_dilem", "jednotek"),
    ("odběr elektřiny nebytových prostor DV", "elektro", None, "submeter", ""),
]

# zpusob -> (predpona kodu meridla klice, ktere plochy)
PODMERY = {"voda": "W_", "teplo": "T_", "elektro": "E_"}


class Command(BaseCommand):
    help = "Založí pro areál DV položky zásobníku služeb a klíče na aktivní karty."

    def add_arguments(self, parser):
        parser.add_argument("--provest", action="store_true", help="Skutečně zapsat.")

    def handle(self, *args, **volby):
        site = Site.objects.filter(name="DV").first()
        if site is None:
            raise CommandError("Areál DV nenalezen.")
        zapsat = volby["provest"]
        if not zapsat:
            self.stdout.write(self.style.WARNING("NÁHLED - nic se nezapisuje (--provest).\n"))

        # plocha -> (aktivni karta, Plocha) - Plocha se vede na Klici zvlast,
        # ClientCard.unit je starsi pole a u karet s vic plochami je prazdne
        karty, plochy_dle_nazvu = {}, {}
        for cu in (CardUnit.objects
                   .filter(unit__site=site, card__is_active=True)
                   .select_related("card__client", "unit")):
            karty[cu.unit.name] = cu.card
            plochy_dle_nazvu[cu.unit.name] = cu.unit
        meridla = {m.code: m for m in Meter.objects.filter(site=site)}

        self.stdout.write("obsazené plochy: {}".format(", ".join(sorted(karty))))

        for nazev, trida, kod_meridla, zpusob, popis_vahy in POLOZKY:
            self.stdout.write(self.style.MIGRATE_HEADING("\n{} [{}]".format(nazev, trida)))

            meridlo = meridla.get(kod_meridla) if kod_meridla else None
            if kod_meridla and meridlo is None:
                self.stderr.write("   ✗ měřidlo {} neexistuje, přeskakuji".format(kod_meridla))
                continue

            polozka = ServicePoolItem.objects.filter(site=site, name=nazev).first()
            if polozka is None:
                self.stdout.write("   položka: ZALOŽIT{}".format(
                    "  (měřidlo {})".format(kod_meridla) if kod_meridla else ""))
                if zapsat:
                    polozka = ServicePoolItem.objects.create(
                        site=site, name=nazev, invoice_class=trida, meter=meridlo,
                        default_allocation_type=(
                            AllocationKey.AllocationType.WEIGHTED_COUNT if zpusob == "submeter"
                            else AllocationKey.AllocationType.WEIGHTED_COUNT
                        ),
                        weight_unit_label=popis_vahy,
                    )
            else:
                self.stdout.write("   položka už existuje")

            # ktere plochy se na polozce podileji
            if zpusob == "submeter" and nazev.startswith("odběr elektřiny"):
                plochy = [p for p in S_ELEKTROMEREM if p in karty]
            elif zpusob == "rovnym_dilem_bez_prizemi":
                plochy = [p for p in sorted(karty) if p not in BEZ_VYTAHU]
            else:
                plochy = sorted(karty)

            predpona = PODMERY.get(trida, "")
            for plocha in plochy:
                karta = karty[plocha]
                if polozka is not None and AllocationKey.objects.filter(
                        service_item=polozka, client_card=karta).exists():
                    self.stdout.write("      {:4} {:24} klíč už existuje".format(
                        plocha, karta.client.name[:24]))
                    continue

                if zpusob == "submeter":
                    kod = "{}{}".format(predpona, plocha)
                    podmer = meridla.get(kod)
                    if podmer is None:
                        self.stderr.write("      ✗ {:4} měřidlo {} neexistuje".format(plocha, kod))
                        continue
                    popis = "podměr {}".format(kod)
                    udaje = dict(allocation_type=AllocationKey.AllocationType.WEIGHTED_COUNT,
                                 meter=podmer)
                else:
                    popis = "rovným dílem (váha 1)"
                    udaje = dict(allocation_type=AllocationKey.AllocationType.WEIGHTED_COUNT,
                                 value=Decimal("1"))

                self.stdout.write(self.style.SUCCESS("      {:4} {:24} {}".format(
                    plocha, karta.client.name[:24], popis)))
                if zapsat and polozka is not None:
                    AllocationKey.objects.create(
                        service_item=polozka, client_card=karta,
                        unit=plochy_dle_nazvu[plocha], **udaje)

            if zpusob.startswith("rovnym_dilem"):
                self.stdout.write("      → dělí se mezi {} jednotek{}".format(
                    len(plochy),
                    " (bez {})".format(", ".join(BEZ_VYTAHU))
                    if zpusob.endswith("prizemi") else ""))

        if not zapsat:
            self.stdout.write(self.style.WARNING("\nNic zapsáno nebylo (--provest)."))
        else:
            self.stdout.write(self.style.SUCCESS("\nHotovo."))
        self.stdout.write(
            "\nDál je potřeba zadat Náklady za období (faktury) a u měřených "
            "položek Ceník, jinak se nemá z čeho počítat."
        )
