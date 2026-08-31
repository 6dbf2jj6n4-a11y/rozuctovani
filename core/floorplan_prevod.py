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


#: co se má stát na straně nájemce
REZIM_NOVA = "nova"          # založit úplně novou Kartu
REZIM_NAVAZAT = "navazat"    # jeho běžící Kartu uzavřít a navázat novou s plochami navíc
REZIM_PRIDAT = "pridat"      # plochy přidat rovnou do běžící Karty


def karta_klienta_k_datu(klient, datum):
    """Karta klienta platná k datu, nebo None."""
    from django.db.models import Q

    from core.models import ClientCard

    return (
        ClientCard.objects.filter(client=klient, is_active=True, valid_from__lte=datum)
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=datum))
        .order_by("-valid_from")
        .first()
    )


class Prevod:
    """Co se stane - k zobrazení i k provedení."""

    def __init__(self, klient, datum, sazba=None, cil_karta=None, rezim=REZIM_NOVA):
        self.klient = klient
        self.datum = datum
        self.sazba = sazba
        self.cil_karta = cil_karta
        self.rezim = rezim if cil_karta else REZIM_NOVA
        self.cil_plosne_klice = []
        self.zdroje = []        # [{card, plochy, zbyde_m2, plosne_klice, ostatni_klice}]
        self.nove_plochy = []   # [Unit] pro novou Kartu nájemce
        self.bez_karty = []     # [Unit] plochy, které dosud nikdo nedržel
        self.poznamky = []      # co se přeskočí - převod může proběhnout dál
        self.potize = []        # blokující - převod nemá co dělat
        self.uz_drzi = []       # [(Karta, [Unit])] - plochy, které nájemce už má
        self.budouci = []       # [{card, plochy, zbyde_ploch}] - Karty, které
                                # začínají AŽ PO datu převodu a plochu mají taky

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

    @property
    def cil_m2_pred(self):
        return _soucet_m2(self.cil_karta) if self.cil_karta else Decimal("0")

    @property
    def cil_m2_po(self):
        return self.cil_m2_pred + self.prevadene_m2


def priprav(units, klient, datum, sazba=None, cil_karta=None, rezim=REZIM_NOVA):
    """Spočítá, co převod udělá. Nic nezapisuje."""
    from core.models import CardUnit

    prevod = Prevod(klient, datum, sazba, cil_karta, rezim)

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

    # Karta, ktera zacina az PO datu prevodu, se do vyberu vyse nevejde -
    # a to i kdyz je najemcova a plochu uz drzi. Bez tehle kontroly by
    # prevod tise zalozil dalsi jeho Kartu s toutez plochou a od zacatku
    # te pozdejsi by obe platily naraz. Viz Daniel 2026-08-26.
    pozdejsi = (
        CardUnit.objects.select_related("card", "unit")
        .filter(unit__in=units, card__is_active=True, card__client=klient,
                card__valid_from__gt=datum)
        .order_by("card__valid_from")
    )
    for cu in pozdejsi:
        prevod.potize.append(
            "%s už plochu %s drží na Kartě %s, která začíná %s – tedy až po "
            "zvoleném datu. Převodem by plocha skončila na dvou jeho Kartách "
            "naráz. Zvol datum od %s dál, nebo plochu přidej přímo na té Kartě."
            % (klient, cu.unit.name, cu.card.description,
               cu.card.valid_from.strftime("%-d. %-m. %Y"),
               cu.card.valid_from.strftime("%-d. %-m. %Y"))
        )

    # Jedna Karta = jeden areal (viz ClientCard.clean). Prevod plochy do
    # bezici Karty jineho arealu by takovou Kartu vyrobil a ta by pak sla
    # jen precist, ne ulozit. Viz Daniel 2026-09-08.
    if cil_karta is not None and rezim != REZIM_NOVA:
        cizi = {s.name for s in cil_karta.sites()} - {u.site.name for u in units}
        vlastni = {u.site.name for u in units}
        if cizi and vlastni - {s.name for s in cil_karta.sites()}:
            prevod.potize.append(
                "Karta %s patří areálu %s, ale převádíš plochy z %s. Jedna "
                "Karta patří vždy jednomu areálu - zvol „Založit další "
                "samostatnou kartu“."
                % (cil_karta.description, ", ".join(sorted(cizi)),
                   ", ".join(sorted(vlastni)))
            )

    for unit in units:
        if unit.id not in drzene:
            prevod.bez_karty.append(unit)

    # Karty, které začínají AŽ PO datu převodu a převáděnou plochu mají taky.
    # Do dotazu výše se nevejdou (filtruje na platnost k datu), a přesně kvůli
    # tomu zůstávala plocha viset na budoucí Kartě původního držitele -
    # Daniel 2026-08-26, kancelář AB 3.14. Nezavírají se: ještě nezačaly,
    # takže se z nich plocha prostě odebere.
    budouci_radky = (
        CardUnit.objects.select_related("card", "card__client", "unit")
        .filter(unit__in=units, card__is_active=True, card__valid_from__gt=datum)
        .exclude(card__client_id=klient.id)
        .order_by("card__valid_from")
    )
    budouci_podle_karty = {}
    for cu in budouci_radky:
        budouci_podle_karty.setdefault(cu.card, []).append(cu)

    for card, cus in budouci_podle_karty.items():
        zbyde = card.card_units.count() - len(cus)
        if zbyde <= 0:
            # Karta bez jediné Plochy je podle ClientCard.clean neplatná,
            # takže ji radši nechám být a řeknu proč - ať se s ní rozhodne
            # člověk (zrušit? nechat na jiné ploše?).
            prevod.poznamky.append(
                "Karta %s (%s, od %s) má převáděné plochy jako JEDINÉ – "
                "neodebírám je, karta by zůstala prázdná. Vyřeš ji ručně."
                % (card, card.client, card.valid_from.strftime("%-d. %-m. %Y"))
            )
            continue
        prevod.budouci.append({
            "card": card,
            "plochy": [cu.unit for cu in cus],
            "zbyde_ploch": zbyde,
        })

    for card, cus in podle_karty.items():
        if card.client_id == klient.id:
            # plochu, kterou nájemce sám drží, nelze převádět - skončila by
            # na dvou jeho Kartách naráz
            prevod.uz_drzi.append((card, [cu.unit for cu in cus]))
            continue
        # Karta začínající přesně v den převodu se nezavírá - ještě za žádné
        # období neúčtovala, takže se plochy prostě odeberou rovnou z ní.
        # Jinak by valid_to vyšlo o den dřív než valid_from.
        rovnou = bool(card.valid_from and card.valid_from == datum)

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
            "rovnou": rovnou,
        })
        prevod.nove_plochy.extend(cu.unit for cu in cus)

    if prevod.cil_karta:
        soucet = _soucet_m2(prevod.cil_karta)
        prevod.cil_plosne_klice = [
            k for k in prevod.cil_karta.allocation_keys.select_related("service_item").all()
            if _je_plosny(k, soucet)
        ]
        if prevod.rezim == REZIM_PRIDAT and prevod.cil_karta.valid_from < datum:
            prevod.poznamky.append(
                "Karta %s běží už od %s. Přidáním plochy se změní i období, která "
                "od té doby proběhla – pokud to není záměr, zvol navázání novou Kartou."
                % (prevod.cil_karta.description,
                   prevod.cil_karta.valid_from.strftime("%-d. %-m. %Y"))
            )

    if not prevod.nove_plochy and not prevod.bez_karty:
        if prevod.uz_drzi:
            prevod.potize.append(
                "Všechny vybrané plochy už %s drží: %s. Převádět je znovu nedává "
                "smysl – byly by na dvou jeho Kartách naráz. Když je potřebuješ mít "
                "na jiné Kartě, uprav to přímo na Kartách klienta."
                % (klient, "; ".join(
                    "%s na kartě %s (od %s)"
                    % (", ".join(u.name for u in plochy), karta.description,
                       karta.valid_from.strftime("%-d. %-m. %Y"))
                    for karta, plochy in prevod.uz_drzi))
            )
        else:
            prevod.potize.append("Není co převádět.")
    elif prevod.uz_drzi:
        prevod.poznamky.append(
            "Vynechávám plochy, které %s už drží: %s."
            % (klient, "; ".join(
                "%s (karta %s)" % (", ".join(u.name for u in plochy), karta.description)
                for karta, plochy in prevod.uz_drzi))
        )
    return prevod


@transaction.atomic
def proved(prevod):
    """Provede připravený převod. Vrací novou Kartu nájemce."""
    from core.models import CardUnit, ClientCard

    for zdroj in prevod.zdroje:
        card = zdroj["card"]

        if zdroj.get("rovnou"):
            # Karta začíná v den převodu - plochy z ní jen zmizí
            puvodni_soucet = _soucet_m2(card)
            CardUnit.objects.filter(
                card=card, unit__in=[u.id for u in zdroj["plochy"]]
            ).delete()
            zbyva = _soucet_m2(card)
            for klic in card.allocation_keys.all():
                if _je_plosny(klic, puvodni_soucet):
                    klic.value = zbyva
                    klic.save(update_fields=["value"])
            continue

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

    # 2b) Karty, které teprve začnou - plocha se z nich jen odebere
    for budouci in prevod.budouci:
        card = budouci["card"]
        puvodni_soucet = _soucet_m2(card)
        CardUnit.objects.filter(
            card=card, unit__in=[u.id for u in budouci["plochy"]]
        ).delete()
        zbyva = _soucet_m2(card)
        for klic in card.allocation_keys.all():
            if _je_plosny(klic, puvodni_soucet):
                klic.value = zbyva
                klic.save(update_fields=["value"])

    # 3) Karta nájemce - podle zvoleného režimu
    if prevod.rezim == REZIM_PRIDAT:
        # plochy jdou rovnou do běžící Karty; náhled upozornil, že se tím
        # mění i období, která od jejího začátku proběhla
        nova = prevod.cil_karta
        stary_soucet = _soucet_m2(nova)
    elif prevod.rezim == REZIM_NAVAZAT:
        # běžící Karta se uzavře a od data na ni naváže nová s plochami navíc
        cil = prevod.cil_karta
        stary_soucet = _soucet_m2(cil)
        nova = cil.create_exact_copy(valid_from=prevod.datum, is_active=True)
        nova.valid_to = cil.valid_to
        nova.description = ""
        nova.note = (
            "Pokračování karty po přidání ploch %s k %s."
            % (", ".join(u.name for u in prevod.vsechny_plochy),
               prevod.datum.strftime("%-d. %-m. %Y"))
        )
        nova.save()
        cil.valid_to = prevod.den_uzavreni
        cil.save(update_fields=["valid_to"])
    else:
        nova = ClientCard(client=prevod.klient, valid_from=prevod.datum, is_active=True)
        nova.note = "Vznikla převodem ploch z plánku."
        nova.save()
        stary_soucet = Decimal("0")

    for unit in prevod.vsechny_plochy:
        CardUnit.objects.get_or_create(
            card=nova, unit=unit,
            defaults={"area_m2_override": unit.area_m2, "rate_per_m2": prevod.sazba},
        )

    # plošné klíče, které Karta už měla, musí povyrůst o přibylou výměru
    if stary_soucet:
        novy_soucet = _soucet_m2(nova)
        for klic in nova.allocation_keys.all():
            if _je_plosny(klic, stary_soucet):
                klic.value = novy_soucet
                klic.save(update_fields=["value"])

    # Klíče nové Karty vznikly z Výchozích služeb ploch (UnitService) uvnitř
    # CardUnit.save() -> create_default_keys(). Ze staré Karty se ZÁMĚRNĚ nic
    # nekopíruje: klíč patří k ploše, ne ke Kartě, ze které se zrovna převádí.
    # Když plocha Výchozí služby nemá, vznikne Karta bez klíčů a doplní se
    # ručně - náhled na to upozorní dopředu (Prevod.klice_z_ploch).
    return nova
