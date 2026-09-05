"""
Preklicovani tepla NJ z poctu radiatoru na VYTAPENOU PLOCHU (m2).

Puvodni model (viz preklicovat_teplo_nj) delil naklad nejdriv mezi dve
"meridla" - T_SPOLECNA (radiatory ve spolecnych prostorach) a
T_INDIVIDUALNI (radiatory v kancelarich) - a teprve uvnitr skupin mezi
klienty, podle poctu osob resp. radiatoru.

Daniel 2026-09-05: ta dve meridla ve skutecnosti nic nemeri, ve vsech
obdobich maji stejnou hodnotu (10 a 20), takze drzi jen pevny pomer 2:1.
Navic pocet radiatoru nebere ohled na velikost mistnosti. Spravedlivejsi
je delit podle vytapene plochy - ta je od migrace 0100 primo na Prostoru
(Unit.is_heated / heated_area_m2).

Novy model: kazda Karta dostane JEDINY vazeny klic bez meridla s vahou
= soucet vytapenych m2 jejich Prostoru. Zadne deleni na spolecnou
a individualni cast - radiatory na WC a chodbach zaplati vsichni
pomerem svych metru, coz je presne ono.

Co se NEMENI:
  * pevne castky (FSL CZ ma 750 Kc/mesic) - ty zustavaji, jak jsou.
    Diky tomu FSL prispiva dal, i kdyz zadnou vytapenou plochu nema.
  * priznak "Fakturovat" (is_billed) se prenese z puvodniho klice -
    pausalni klienti zustanou pausalni.
  * Karta bez jedine vytapene plochy klic nedostane a teplo neplati
    (EVUM Motors - zadny radiator uz dnes).

VYCHOZI je jen NAHLED, zapisuje se az s --provest.

Pouziti:
  python manage.py preklicovat_teplo_nj_m2
  python manage.py preklicovat_teplo_nj_m2 --provest
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import AllocationKey, CardUnit, ServicePoolItem, Site

STARA_MERIDLA = ("T_SPOLECNA", "T_INDIVIDUALNI")


def _cislo(d):
    """Decimal.normalize() by ze 140 udelal "1.4E+2"."""
    return ("%f" % d).rstrip("0").rstrip(".").replace(".", ",")
POPIS_VAHY = "m² vytápěné plochy"


class Command(BaseCommand):
    help = "Překlíčuje teplo NJ z počtu radiátorů na vytápěnou plochu (m²)."

    def add_arguments(self, parser):
        parser.add_argument("--provest", action="store_true", help="Skutečně zapsat.")

    def handle(self, *args, **volby):
        zapsat = volby["provest"]
        site = Site.objects.filter(name="NJ").first()
        if site is None:
            raise CommandError("Areál NJ neexistuje.")
        polozka = ServicePoolItem.objects.filter(site=site, name="hlavní odběr teplo NJ").first()
        if polozka is None:
            raise CommandError("Položka „hlavní odběr teplo NJ“ neexistuje.")

        if not zapsat:
            self.stdout.write(self.style.WARNING("NÁHLED - nic se nezapisuje (--provest).\n"))

        # vytapena plocha podle Karty
        plochy, popis = {}, {}
        for cu in (CardUnit.objects
                   .filter(unit__site=site, card__is_active=True)
                   .select_related("card__client", "unit")):
            plocha = cu.vytapena_plocha
            if plocha:
                plochy[cu.card_id] = plochy.get(cu.card_id, Decimal("0")) + plocha
                popis.setdefault(cu.card_id, []).append(
                    "%s %s m²" % (cu.unit.name, _cislo(plocha)))

        stare = list(
            polozka.allocation_keys
            .filter(meter__code__in=STARA_MERIDLA)
            .select_related("client_card__client", "meter")
        )
        # "Fakturovat" se prenese z puvodniho klice - kdyz to mel klient
        # v najmu, ma to tam zustat
        fakturovat = {}
        for k in stare:
            fakturovat[k.client_card_id] = fakturovat.get(k.client_card_id, True) and k.is_billed

        karty = {k.client_card_id: k.client_card for k in stare}
        for card_id in plochy:
            if card_id not in karty:
                karty[card_id] = CardUnit.objects.filter(card_id=card_id).first().card

        self.stdout.write(self.style.MIGRATE_HEADING(
            "nové klíče (jeden na kartu, váha = vytápěná plocha)"))
        celkem = Decimal("0")
        for card_id, karta in sorted(karty.items(), key=lambda x: str(x[1].client)):
            plocha = plochy.get(card_id, Decimal("0"))
            if not plocha:
                self.stderr.write("   {:30} bez vytápěné plochy - klíč se nezaloží".format(
                    str(karta.client)[:30]))
                continue
            celkem += plocha
            self.stdout.write(self.style.SUCCESS(
                "   {:30} {:>8} m²  fakturovat={}  ({})".format(
                    str(karta.client)[:30], _cislo(plocha),
                    "ano" if fakturovat.get(card_id, True) else "v nájmu",
                    ", ".join(sorted(popis.get(card_id, []))))))
        self.stdout.write("   celkem {} m²".format(_cislo(celkem)))

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\nruší se klíče na {} ({})".format(" a ".join(STARA_MERIDLA), len(stare))))
        pevne = polozka.allocation_keys.filter(allocation_type="fixed_amount").count()
        if pevne:
            self.stdout.write("pevné částky zůstávají beze změny: {}".format(pevne))

        if not zapsat:
            self.stdout.write(self.style.WARNING("\nNic zapsáno nebylo (--provest)."))
            return

        with transaction.atomic():
            for k in stare:
                k.delete()
            for card_id, karta in karty.items():
                plocha = plochy.get(card_id, Decimal("0"))
                if not plocha:
                    continue
                AllocationKey.objects.create(
                    service_item=polozka, client_card=karta, meter=None,
                    allocation_type=AllocationKey.AllocationType.WEIGHTED_COUNT,
                    value=plocha, is_billed=fakturovat.get(card_id, True),
                )
            polozka.weight_unit_label = POPIS_VAHY
            polozka.save(update_fields=["weight_unit_label"])
        self.stdout.write(self.style.SUCCESS("\nHotovo."))
