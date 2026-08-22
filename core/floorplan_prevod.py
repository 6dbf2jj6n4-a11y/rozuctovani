"""Převod ploch mezi Kartami z plánku.

Když si nájemce vezme plochu, která dosud patřila někomu jinému (typicky
pronajímateli), nestačí ji na Kartě přepsat - tím by se změnila i už
uzavřená období. Správně se stávající Karta k datu **uzavře** a od téhož
data vzniknou Karty nové: pokračovací pro původního držitele (bez
převáděných ploch) a nová pro nájemce (s nimi).

Modul počítá jen s daty, žádné view ani formulář - aby šel převod nejdřív
ukázat k odsouhlasení (:func:`priprav`) a teprve pak provést
(:func:`proved`). Danielova podmínka: nic se nezapíše dřív, než uvidí,
co přesně se stane.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction

#: přípona v Popisu pokračovací Karty, aby bylo poznat, proč vznikla
PRIZNAK_PRESUNU = "(část přesunuta)"

#: typy klíčů, jejichž hodnota je výměra - přepočítají se podle m²
PLOSNE_TYPY = ("weighted_count", "area_price", "submeter")


def _soucet_m2(card):
    return sum((cu.area_m2 or Decimal("0")) for cu in card.card_units.all())


def _je_plosny(klic, soucet_karty):
    """Klíč se považuje za plošný, když jeho hodnota sedí na součet m² karty.

    Spolehlivější než hádat podle názvu položky: klíče na teplo (počet
    radiátorů), vodu (počet osob) nebo internet (pevná částka) mají hodnoty,
    které s výměrou nesouvisí, a nesmí se přepočítávat.
    """
    return (
        klic.allocation_type in PLOSNE_TYPY
        and klic.value is not None
        and soucet_karty
        and Decimal(klic.value) == Decimal(soucet_karty)
    )


class Prevod:
    """Co se stane - k zobrazení i k provedení."""

    def __init__(self, klient, datum, sazba=None):
        self.klient = klient
        self.datum = datum
        self.sazba = sazba
        self.zdroje = []        # [{card, plochy, zbyde_m2, plosne_klice, ostatni_klice}]
        self.nove_plochy = []   # [Unit] pro novou Kartu nájemce
        self.bez_karty = []     # [Unit] plochy, které dosud nikdo nedržel
        self.poznamky = []      # co se přeskočí - převod může proběhnout dál
        self.potize = []        # blokující - převod nemá co dělat

    @property
    def klice_z_ploch(self):
        """True, když aspoň jedna převáděná plocha má Výchozí služby.

        Z těch si nová Karta odvodí klíče sama. Ze staré Karty se nekopíruje
        nic, takže když je False, vznikne Karta bez klíčů a doplní se ručně -
        náhled na to musí upozornit dopředu.
        """
        return any(u.unit_services.exists() for u in self.vsechny_plochy)

    @property
    def vsechny_plochy(self):
        """Plochy pro novou Kartu, každá jen jednou.

        Jedna plocha může viset na víc Kartách naráz (překrývající se
        platnosti, pozůstatek po importu). Bez odstranění duplicit by nová
        Karta chtěla dvě stejné Plochy a spadla by na unique_together.
        """
        podle_id = {}
        for unit in list(self.nove_plochy) + list(self.bez_karty):
            podle_id.setdefault(unit.id, unit)
        return list(podle_id.values())

    @property
    def prevadene_m2(self):
        return sum((u.area_m2 or Decimal("0")) for u in self.vsechny_plochy)

    @property
    def den_uzavreni(self):
        return self.datum - timedelta(days=1)


def priprav(units, klient, datum, sazba=None):
    """Spočítá, co převod udělá. Nic nezapisuje."""
    from core.models import CardUnit

    prevod = Prevod(klient, datum, sazba)

    from django.db.models import Q

    # jen Karty platné K DATU převodu - už uzavřená Karta se nesmí zavírat
    # znovu a její plochy dávno drží někdo jiný
    radky = (
        CardUnit.objects.select_related("card", "card__client", "unit")
        .filter(unit__in=units, card__is_active=True, card__valid_from__lte=datum)
        .filter(Q(card__valid_to__isnull=True) | Q(card__valid_to__gte=datum))
        .order_by("card__valid_from")
    )
    podle_karty = {}
    drzene = set()
    for cu in radky:
        podle_karty.setdefault(cu.card, []).append(cu)
        drzene.add(cu.unit_id)

    for unit in units:
        if unit.id not in drzene:
            prevod.bez_karty.append(unit)

    for card, cus in podle_karty.items():
        if card.client_id == klient.id:
            prevod.poznamky.append(
                "%s už drží %s – přeskakuje se."
                % (klient, ", ".join(cu.unit.name for cu in cus))
            )
            continue
        if card.valid_from and card.valid_from >= datum:
            prevod.poznamky.append(
                "Karta %s začíná %s, tedy až po zvoleném datu – přeskakuje se, "
                "jinak by se uzavřela dřív, než začne."
                % (card, card.valid_from.strftime("%-d. %-m. %Y"))
            )
            continue

        soucet = _soucet_m2(card)
        odchazi = sum((cu.area_m2 or Decimal("0")) for cu in cus)
        klice = list(card.allocation_keys.select_related("service_item").all())
        prevod.zdroje.append({
            "card": card,
            "plochy": [cu.unit for cu in cus],
            "odchazi_m2": odchazi,
            "zbyde_m2": soucet - odchazi,
            "zbyde_ploch": card.card_units.count() - len(cus),
            "plosne_klice": [k for k in klice if _je_plosny(k, soucet)],
            "ostatni_klice": [k for k in klice if not _je_plosny(k, soucet)],
        })
        prevod.nove_plochy.extend(cu.unit for cu in cus)

    if not prevod.nove_plochy and not prevod.bez_karty:
        prevod.potize.append("Není co převádět.")
    return prevod


@transaction.atomic
def proved(prevod):
    """Provede připravený převod. Vrací novou Kartu nájemce."""
    from core.models import CardUnit, ClientCard

    for zdroj in prevod.zdroje:
        card = zdroj["card"]

        # 1) pokračovací Karta původního držitele - kopíruje se DŘÍV, než se
        #    originál uzavře, aby si nepřenesla jeho nové valid_to
        if zdroj["zbyde_ploch"]:
            pokracovani = card.create_exact_copy(valid_from=prevod.datum, is_active=True)
            pokracovani.valid_to = card.valid_to
            pokracovani.description = ""      # doplní se podle konvence v save()
            pokracovani.note = (
                "Pokračování karty po převodu ploch %s na %s k %s."
                % (", ".join(u.name for u in zdroj["plochy"]), prevod.klient,
                   prevod.datum.strftime("%-d. %-m. %Y"))
            )
            pokracovani.save()
            # ať je v seznamu Karet na první pohled poznat, proč jich má
            # klient v jednom roce víc - Danielovo přání
            pokracovani.description = "%s %s" % (pokracovani.description, PRIZNAK_PRESUNU)
            pokracovani.save(update_fields=["description"])

            CardUnit.objects.filter(
                card=pokracovani, unit__in=[u.id for u in zdroj["plochy"]]
            ).delete()

            zbyva = _soucet_m2(pokracovani)
            for klic in pokracovani.allocation_keys.all():
                if _je_plosny(klic, _soucet_m2(card)):
                    klic.value = zbyva
                    klic.save(update_fields=["value"])

        # 2) uzavřít původní Kartu
        card.valid_to = prevod.den_uzavreni
        card.save(update_fields=["valid_to"])

    # 3) nová Karta nájemce
    nova = ClientCard(client=prevod.klient, valid_from=prevod.datum, is_active=True)
    nova.note = "Vznikla převodem ploch z plánku."
    nova.save()

    for unit in prevod.vsechny_plochy:
        CardUnit.objects.create(
            card=nova, unit=unit,
            area_m2_override=unit.area_m2,
            rate_per_m2=prevod.sazba,
        )

    # Klíče nové Karty vznikly z Výchozích služeb ploch (UnitService) uvnitř
    # CardUnit.save() -> create_default_keys(). Ze staré Karty se ZÁMĚRNĚ nic
    # nekopíruje: klíč patří k ploše, ne ke Kartě, ze které se zrovna převádí.
    # Když plocha Výchozí služby nemá, vznikne Karta bez klíčů a doplní se
    # ručně - náhled na to upozorní dopředu (Prevod.klice_z_ploch).
    return nova
