"""
Billing engine - vypocet rozuctovani za jedno obdobi.

Postup (shrnuti dohodnute logiky):

1. Pro kazdou polozku Zasobniku v danem obdobi se najde skutecna
   fakturovana castka (CostEntry). Bez ni se polozka pro toto
   obdobi neuctuje (napr. odklizeni snehu v lete - zadny CostEntry
   = zadne naklady).

2. Pokud ma polozka prirazene mericí (energie):
   - spocitaji se "PODILY" jednotlivych karet klientu na zaklade
     odectu (vlastni spotreba mericiho minus podruzna mericí =
     "spolecna" spotreba),
   - klienti s klicem typu SUBMETER dostanou podil = jejich
     namerena spotreba / celkova namerena spotreba hlavniho mericiho,
   - "spolecna" spotreba se dale rozdeli mezi klienty s klici
     percent / area_ratio / person_count / equal_split (vazenymi
     podily, viz krok 4),
   - rozdil mezi namerenym mnozstvim a mnozstvim, ze ktereho
     vychazi faktura dodavatele, se timto automaticky rozpousti
     do vysledne castky (pracujeme s podily, ne s absolutnimi Kc/kWh).

3. Pokud polozka neni merena, podily se pocitaji primo z klicu
   percent / area_ratio / person_count / equal_split (krok 4).

4. Vazene podily: kazdy klic ma "zakladni vahu" (procento, m2,
   pocet osob, nebo 1 pro rovny dil). Tato vaha se vynasobi
   pomerem aktivnich dni karty klienta v danem obdobi ku celkovemu
   poctu dni obdobi. Vysledne efektivni vahy se normalizuji tak,
   aby jejich soucet byl 1 (100 %) - "uvolneny" podil po castecne
   aktivnich kartach se tak rozpusti mezi ostatni.

5. Klice typu FIXED_AMOUNT: dany klient zaplati pevnou castku,
   ktera se odecte z celkove castky polozky. Zbytek se rozpocita
   mezi ostatni klienty podle kroku 2-4.

6. Vysledek se ulozi do BillingLine (castka + podil + JSON detail
   vypoctu pro auditovatelnost).

Pozn.: jde o prvni funkcni verzi - chybejici odecty, nulove
celkove vahy apod. jsou osetreny tak, ze se polozka/karta
vynecha a duvod se zaznamena do `warnings` ve vraceném souhrnu.
Doporucuji pred ostrym pouzitim projit a doplnit dle realnych dat.

Reprodukovatelnost v case: jakmile je Obdobi uzavrene (Period.status
== CLOSED), tato funkce odmita prepocet (viz BillingPeriodClosedError).
BillingLine radky uzavreneho obdobi tak zustavaji navzdy tim, co bylo
skutecne vyuctovano - i kdyz se pozdeji zmeni karty klientu, klice
nebo ceny, ktere do vypoctu vstupovaly. Pro opravu je potreba obdobi
vedome znovu otevrit (admin akce u Obdobi).
"""
from decimal import Decimal

from django.db import transaction

from core.models import AllocationKey, BillingLine, CostEntry, Period, PriceList, ServicePoolItem


class BillingPeriodClosedError(Exception):
    """Obdobi je uzavrene (Period.status == CLOSED) - prepocet neni povolen."""

# Typy klicu, ktere prispivaji absolutni Kc castkou primo (mimo vazene podily) -
# 'Pevna castka' ma castku ulozenou primo, 'Plocha x cena/m2' se dopocitava
# z Ceniku pro dane obdobi (viz _fixed_amount_for).
ABSOLUTE_AMOUNT_TYPES = (
    AllocationKey.AllocationType.FIXED_AMOUNT,
    AllocationKey.AllocationType.AREA_PRICE,
)


def _fixed_amount_for(key, service_item, period, warnings):
    """Vrati absolutni mesicni Kc castku pro klic typu FIXED_AMOUNT/AREA_PRICE."""
    if key.allocation_type == AllocationKey.AllocationType.AREA_PRICE:
        price = PriceList.get_price_for_period(service_item, period)
        if price is None:
            warnings.append(
                f"{service_item}: klíč 'Plocha × cena/m²' pro kartu {key.client_card} "
                f"nemá cenu v Ceníku pro toto ani žádné dřívější období - karta vynechána."
            )
            return None
        return ((key.value or Decimal("0")) * price / 12).quantize(Decimal("0.01"))
    return key.value or Decimal("0")


def _weighted_shares(keys, period, by_key_out=None):
    """
    Spocita normalizovane podily (soucet = 1) pro seznam klicu
    typu percent / area_ratio / person_count / equal_split,
    s prihlednutim k aktivnim dnum karty v obdobi.

    Vraci dict {client_card_id: Decimal podil}.

    `by_key_out`: volitelny dict, do ktereho se navic (pro auditovaci
    detail po klicich - viz billing/key_detail.py) zapise podil PO
    JEDNOTLIVYCH klicich {allocation_key_id: Decimal podil}, normalizovany
    stejne jako vysledek po kartach. Nema zadny vliv na navratovou hodnotu
    ani na vypocet - pokud zustane None (vychozi, pouziva `calculate_period`),
    chovani funkce je zcela beze zmeny.
    """
    period_start, period_end = period.date_range()
    days_in_period = Decimal(period.days_in_period)

    raw_weights = {}
    raw_weights_by_key = {}
    for key in keys:
        card = key.client_card
        active_days = card.active_days_in_period(period_start, period_end)
        if active_days <= 0:
            continue

        if key.allocation_type == AllocationKey.AllocationType.AREA_RATIO:
            base = card.unit.area_m2 or Decimal("0")
        elif key.allocation_type in (
            AllocationKey.AllocationType.PERSON_COUNT,
            AllocationKey.AllocationType.WEIGHTED_COUNT,
        ):
            base = key.value or Decimal("0")
        elif key.allocation_type == AllocationKey.AllocationType.EQUAL_SPLIT:
            base = Decimal("1")
        elif key.allocation_type == AllocationKey.AllocationType.SUBMETER:
            # Sem se klice typu SUBMETER dostanou jen pri lokalnim deleni
            # JEDNOHO konkretniho podruzneho meridla mezi vice karet, ktere
            # ho sdili (viz _consumption_shares) - value je pak vaha pro
            # rozdeleni spotreby TOHOTO meridla mezi ne.
            base = key.value or Decimal("0")
        else:  # PERCENT
            base = key.value or Decimal("0")

        effective_weight = base * (Decimal(active_days) / days_in_period)
        raw_weights[card.id] = raw_weights.get(card.id, Decimal("0")) + effective_weight
        if by_key_out is not None:
            raw_weights_by_key[key.id] = effective_weight

    total = sum(raw_weights.values())
    if total == 0:
        return {}
    if by_key_out is not None:
        for key_id, weight in raw_weights_by_key.items():
            by_key_out[key_id] = weight / total
    return {card_id: weight / total for card_id, weight in raw_weights.items()}


def _consumption_shares(service_item, period, warnings, by_key_out=None):
    """
    Spocita podily pro polozku, kde se aspon cast klicu opira o skutecnou
    namerenou spotrebu meridla - bud primo pres service_item.meter (hlavni
    meridlo cele polozky), nebo pres jednotliva meridla napojena na
    konkretni klice (AllocationKey.meter), typicky u typu "Podružné
    měřidlo" (submeter), ale muze jim byt napojen i klic typu "Podle vahy"
    (napr. virtualni meridlo se vzorcem jako "spolecna spotreba WC",
    slozene ze souctu par realnych meridel - viz Meter.is_virtual/formula).

    Dva rezimy podle toho, jestli ma polozka nastavene hlavni meridlo:

    1) service_item.meter je nastaveny: "celek" = jeho namerena spotreba.
       Klice napojene na SVE VLASTNI meridlo (seskupene podle meridla -
       vice karet muze sdilet jedno fyzicke meridlo, napr. spolecny
       elektromer pro dva prostory) dostanou podil = spotreba_meridla /
       celek, pripadne rozdeleny mezi sdilejici karty podle vahy. Klice
       BEZ vlastniho meridla dostanou zbytek (co nezachytila zadna
       pojmenovana meridla) rozpocitany podle vahy.

    2) service_item.meter NENI nastaveny (zadne "hlavni" cislo k dispozici,
       jen soucet nakladu za obdobi): "celek" se dopocita jako SOUCET
       spotreby VSECH meridel, na ktera je napojeny nejaky klic polozky
       (kazde meridlo jen jednou, bez ohledu na pocet klicu/karet na nem) -
       kazda takova skupina pak dostane podil = jeji spotreba / tento
       soucet. Klice BEZ zadneho napojeneho meridla v tomto rezimu nemaji
       fyzikalni zaklad pro urceni podilu - vynechaji se s varovanim.

    Vraci dvojici (shares, total_consumption):
      - shares: dict {client_card_id: Decimal podil}, soucet ~= 1, pokud
        se podarilo dohledat vsechny potrebne odecty. Pri chybejicich
        odectech pripoji varovani a chybejici karty vynecha.
      - total_consumption: pouzity "celek" (viz vyse), pro dopocet
        spotreby/ceny za jednotku jednotlivych karet, nebo None, pokud se
        nepodarilo dohledat vubec zadnou spotrebu.

    `by_key_out`: viz _weighted_shares - volitelny dict {allocation_key_id:
    Decimal podil}, jen pro auditovaci detail po klicich. Bez vlivu na
    vysledek ani chovani, pokud zustane None.
    """
    keys = [
        k for k in service_item.allocation_keys.select_related("client_card", "client_card__unit", "meter")
        if k.is_valid_for_period(period) and k.allocation_type not in ABSOLUTE_AMOUNT_TYPES
    ]

    # Klice seskupene podle konkretniho meridla - bez ohledu na typ klice
    # (jak "Podružné měřidlo", tak "Podle váhy" klic muze mit meridlo
    # napojene - viz docstring vyse). Klice BEZ meridla jdou do weight_keys.
    keys_by_meter = {}
    weight_keys = []
    for key in keys:
        if key.meter_id is not None:
            keys_by_meter.setdefault(key.meter_id, []).append(key)
        else:
            weight_keys.append(key)

    main_meter = service_item.meter
    if main_meter is not None:
        total_consumption = main_meter.consumption_for(period)
        if total_consumption is None:
            warnings.append(
                f"{service_item}: chybí odečet měřidla {main_meter} pro období {period} "
                f"nebo předchozí období - položka vynechána."
            )
            return {}, None
        if total_consumption == 0:
            warnings.append(f"{service_item}: nulová spotřeba měřidla {main_meter} - položka vynechána.")
            return {}, None
        implicit_total = False
    else:
        total_consumption = None  # dopocita se nize jako soucet skupin
        implicit_total = True

    shares = {}
    sum_groups = Decimal("0")
    resolved_groups = {}  # meter_id -> (Decimal spotreba, [klice])

    for meter_id, group_keys in keys_by_meter.items():
        group_meter = group_keys[0].meter
        group_consumption = group_meter.consumption_for(period)
        if group_consumption is None:
            cards = ", ".join(str(k.client_card) for k in group_keys)
            warnings.append(
                f"{service_item}: chybí odečet měřidla {group_meter} pro období {period} "
                f"- karty ({cards}) vynechány."
            )
            continue
        resolved_groups[meter_id] = (group_consumption, group_keys)
        sum_groups += group_consumption

    if implicit_total:
        total_consumption = sum_groups
        if total_consumption == 0:
            warnings.append(
                f"{service_item}: nemá hlavní měřidlo a žádné z napojených měřidel nemá "
                f"naměřenou spotřebu pro toto období - položka vynechána."
            )
            return {}, None

    for group_consumption, group_keys in resolved_groups.values():
        contribution = group_consumption / total_consumption

        if len(group_keys) == 1:
            key = group_keys[0]
            shares[key.client_card_id] = shares.get(key.client_card_id, Decimal("0")) + contribution
            if by_key_out is not None:
                by_key_out[key.id] = contribution
        else:
            local_by_key = {} if by_key_out is not None else None
            local_shares = _weighted_shares(group_keys, period, by_key_out=local_by_key)
            if not local_shares:
                cards = ", ".join(str(k.client_card) for k in group_keys)
                warnings.append(
                    f"{service_item}: měřidlo {group_keys[0].meter} sdílí více karet ({cards}), "
                    f"ale žádná z nich nemá pro toto období platnou váhu - jeho spotřeba se "
                    f"nerozpočítala."
                )
                continue
            for card_id, weight in local_shares.items():
                shares[card_id] = shares.get(card_id, Decimal("0")) + weight * contribution
            if by_key_out is not None:
                for key_id, weight in local_by_key.items():
                    by_key_out[key_id] = weight * contribution

    if not implicit_total:
        # Rezim s hlavnim meridlem - co nezachytila zadna pojmenovana
        # skupina (napr. spolecne prostory bez vlastniho meridla) se
        # rozpocita mezi klice BEZ meridla podle vahy.
        residual = total_consumption - sum_groups
        residual_fraction = residual / total_consumption
        if weight_keys and residual_fraction > 0:
            weight_by_key = {} if by_key_out is not None else None
            weight_shares = _weighted_shares(weight_keys, period, by_key_out=weight_by_key)
            for card_id, weight in weight_shares.items():
                shares[card_id] = shares.get(card_id, Decimal("0")) + weight * residual_fraction
            if by_key_out is not None:
                for key_id, weight in weight_by_key.items():
                    by_key_out[key_id] = weight * residual_fraction
        elif residual_fraction != 0 and not weight_keys:
            warnings.append(
                f"{service_item}: zbývá {residual_fraction:.2%} spotřeby (společná část), "
                f"ale žádná karta nemá klíč pro její rozpočítání."
            )
    elif weight_keys:
        # Rezim bez hlavniho meridla - klic bez napojeneho meridla nema
        # fyzikalni zaklad, ze ktereho by sel podil urcit.
        cards = ", ".join(str(k.client_card) for k in weight_keys)
        warnings.append(
            f"{service_item}: karty ({cards}) mají klíč bez napojeného měřidla, ale položka "
            f"nemá hlavní měřidlo - není vůči čemu určit jejich podíl, vynechány."
        )

    return shares, total_consumption


def calculate_period(period, site=None):
    """
    Spocita rozuctovani polozek Zasobniku pro dane obdobi a ulozi
    vysledky do BillingLine (existujici radky pro toto obdobi se
    nahradi).

    Pokud je zadany `site`, pocita se jen za tento areal - smazou a
    prepocitaji se jen BillingLine patrici polozkam tohoto arealu,
    vysledky ostatnich arealu pro stejne obdobi zustanou beze zmeny.
    Bez `site` se pocita (a maze/prepisuje) za vsechny arealy najednou.

    Vraci dict se souhrnem: {"created": int, "warnings": [str, ...]}.

    Vyhodi BillingPeriodClosedError, pokud je `period` uzavrene - viz
    modulovy docstring ("Reprodukovatelnost v case").
    """
    if period.status == Period.Status.CLOSED:
        raise BillingPeriodClosedError(
            f"Období {period} je uzavřené - přepočet není povolen. "
            f"Nejprve ho v adminu znovu otevři (akce u Období)."
        )

    warnings = []
    created = 0

    with transaction.atomic():
        billing_lines = BillingLine.objects.filter(period=period)
        service_items = ServicePoolItem.objects.select_related("meter")
        if site is not None:
            billing_lines = billing_lines.filter(service_item__site=site)
            service_items = service_items.filter(site=site)
        billing_lines.delete()

        for service_item in service_items:
            cost_entry = CostEntry.objects.filter(service_item=service_item, period=period).first()
            cost_source = None
            if cost_entry is not None:
                total_cost = cost_entry.get_amount_czk(period)
                if total_cost is None:
                    warnings.append(
                        f"{service_item} / {period}: náklad je zadaný v jednotkách, ale chybí "
                        f"cena v Ceníku - položka vynechána."
                    )
                    continue
                cost_source = "naklad_za_obdobi"
            elif service_item.default_amount_czk is not None:
                total_cost = service_item.default_amount_czk
                cost_source = "vychozi_castka_polozky"
            else:
                continue  # napr. sezonni sluzba bez nakladu v tomto mesici a bez vychozi castky

            all_keys = list(
                service_item.allocation_keys.select_related("client_card", "client_card__unit", "meter")
            )
            valid_keys = [k for k in all_keys if k.is_valid_for_period(period)]

            fixed_keys = [k for k in valid_keys if k.allocation_type in ABSOLUTE_AMOUNT_TYPES]

            # Fakturovat = vsechny platne klice karty pro tuto polozku maji
            # is_billed=True (typicky je klic jen jeden). Pokud karta nema
            # zadny platny klic (neocekavane), bezpecny vychozi stav je
            # fakturovat, ne naopak.
            billed_by_card = {}
            for key in valid_keys:
                billed_by_card[key.client_card_id] = billed_by_card.get(key.client_card_id, True) and key.is_billed

            period_start, period_end = period.date_range()

            # 1) pevne castky (a plocha x cena/m2) - ty s deduct_from_pool=True se
            # odectou z celkove castky, zbytek (deduct_from_pool=False) klient plati
            # samostatne/navic a nema vliv na to, kolik zbyva k rozpocitani ostatnim
            # kartam. Karta mimo svou platnost (valid_from/valid_to) v tomto obdobi
            # pausal neplati - stejna podminka jako u vazenych podilu (_weighted_shares).
            remaining_cost = total_cost
            fixed_amounts = {}
            # Spotreba/cena za jednotku pro klice typu 'Plocha x cena/m2' (vymera
            # a cena z Ceniku) - u ostatnich absolutnich typu (Pevna castka) zadna
            # fyzikalni jednotka nedava smysl, tam units/price_per_unit zustanou prazdne.
            fixed_units = {}
            fixed_price_per_unit = {}
            for key in fixed_keys:
                if key.client_card.active_days_in_period(period_start, period_end) <= 0:
                    continue
                amount = _fixed_amount_for(key, service_item, period, warnings)
                if amount is None:
                    continue
                fixed_amounts[key.client_card_id] = fixed_amounts.get(key.client_card_id, Decimal("0")) + amount
                if key.allocation_type == AllocationKey.AllocationType.AREA_PRICE:
                    price = PriceList.get_price_for_period(service_item, period)
                    if price is not None:
                        fixed_units[key.client_card_id] = (
                            fixed_units.get(key.client_card_id, Decimal("0")) + (key.value or Decimal("0"))
                        )
                        fixed_price_per_unit[key.client_card_id] = price
                if key.deduct_from_pool:
                    remaining_cost -= amount

            if remaining_cost < 0:
                warnings.append(
                    f"{service_item} / {period}: pevné částky odečítané ze společného nákladu "
                    f"překračují celkový náklad ({total_cost} Kč) - přebytek se nerozpočítává "
                    f"ostatním kartám (jen informativní hláška, zvaž u některých klíčů vypnout "
                    f"'Odečíst z celkového nákladu')."
                )
                # Prebytek se nerozpocitava jako "sleva" spotrebovym kartam.
                remaining_cost = Decimal("0")

            # 2) podily na zbytku castky
            total_consumption = None
            # I bez hlavniho meridla na urovni polozky (service_item.meter)
            # muze mit nektery klic napojene SVE VLASTNI meridlo (typicky
            # "Podružné měřidlo", viz _consumption_shares) - v tom pripade
            # se "celek" dopocita jako soucet spotreby takovych meridel.
            has_meter_keys = any(
                k.meter_id is not None
                for k in valid_keys if k.allocation_type not in ABSOLUTE_AMOUNT_TYPES
            )
            if service_item.meter or has_meter_keys:
                shares, total_consumption = _consumption_shares(service_item, period, warnings)
            else:
                weight_keys = [
                    k for k in valid_keys if k.allocation_type not in ABSOLUTE_AMOUNT_TYPES
                ]
                shares = _weighted_shares(weight_keys, period)
                if not shares and remaining_cost != 0:
                    warnings.append(f"{service_item} / {period}: žádné klíče pro rozpočítání zbylé částky.")

            # Prumerna cena za jednotku namerene spotreby (celkovy naklad polozky /
            # celkova namerena spotreba) - ulozi se u kazde karty s podilem na
            # spotrebe, aby bylo v klientskem vyuctovani videt, jak se k castce
            # doslo (jednotky x cena/jednotku), i kdyz se obdobi pozdeji uzavre.
            share_price_per_unit = None
            if total_consumption:
                share_price_per_unit = (total_cost / total_consumption).quantize(Decimal("0.0001"))

            # 3) sestaveni vysledku
            results = dict(fixed_amounts)
            for card_id, share in shares.items():
                results[card_id] = results.get(card_id, Decimal("0")) + remaining_cost * share

            for card_id, amount in results.items():
                share = shares.get(card_id)

                units = None
                price_per_unit = None
                unit_of_measure = None
                if card_id in fixed_units:
                    units = fixed_units[card_id]
                    price_per_unit = fixed_price_per_unit.get(card_id)
                    unit_of_measure = "m²"
                elif share is not None and total_consumption:
                    units = (share * total_consumption).quantize(Decimal("0.001"))
                    price_per_unit = share_price_per_unit
                    # Bez hlavniho meridla na urovni polozky (implicitni
                    # celek dopocitany z jednotlivych klicovych meridel v
                    # _consumption_shares) neni jedno spolecne meridlo, ze
                    # ktereho by sla vzit jednotka - vezme se z prvniho
                    # klice s napojenym meridlem, jinak zustane prazdna.
                    if service_item.meter:
                        unit_of_measure = service_item.meter.unit_of_measure
                    else:
                        key_with_meter = next((k for k in valid_keys if k.meter_id), None)
                        unit_of_measure = key_with_meter.meter.unit_of_measure if key_with_meter else ""

                BillingLine.objects.create(
                    client_card_id=card_id,
                    period=period,
                    service_item=service_item,
                    amount=amount.quantize(Decimal("0.01")),
                    units=units,
                    share=share,
                    is_billed=billed_by_card.get(card_id, True),
                    calc_detail={
                        "total_cost": str(total_cost),
                        "cost_source": cost_source,
                        "fixed_amount": str(fixed_amounts.get(card_id, Decimal("0"))),
                        "remaining_cost": str(remaining_cost),
                        "share": str(share) if share is not None else None,
                        "price_per_unit": str(price_per_unit) if price_per_unit is not None else None,
                        "unit_of_measure": unit_of_measure,
                    },
                )
                created += 1

    return {"created": created, "warnings": warnings}
