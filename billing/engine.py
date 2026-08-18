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

from core.models import (
    AllocationKey, BillingLine, ClientCard, CostEntry, InvoiceClassColor, MeterReading, Period,
    PriceList, ServicePoolItem,
)


class BillingPeriodClosedError(Exception):
    """Obdobi je uzavrene (Period.status == CLOSED) - prepocet neni povolen."""

# Typy klicu, ktere prispivaji absolutni Kc castkou primo (mimo vazene podily) -
# 'Pevna castka' ma castku ulozenou primo, 'Plocha x cena/m2' se dopocitava
# z Ceniku pro dane obdobi (viz _fixed_amount_for).
ABSOLUTE_AMOUNT_TYPES = (
    AllocationKey.AllocationType.FIXED_AMOUNT,
    AllocationKey.AllocationType.AREA_PRICE,
)


def _meter_provides_consumption(meter, cache=None):
    """Rozliší meridlo skutecne pouzivane pro rozpocet spotreby (realne s
    odecty, nebo virtualni se vzorcem) od meridla napojeneho na klic typu
    "Podle váhy" JEN kvuli Meter.weight_unit_label (napr. "pocet
    radiatoru", viz help_text pole - "jen informativni, na vypocet nema
    vliv"). Bez tohoto rozliseni by kazde takove "popiskove" meridlo bez
    jedineho odectu prepnulo _consumption_shares do rezimu zalozeneho na
    spotrebe a celou polozku vyradilo (chybi odecet -> 0 - viz bug u
    "teplo - spotřeba pelet NJ"/"úklidové služby..."/"odvoz..." NJ).

    Virtualni meridlo bez vyplneneho Vzorce (napr. ODPAD/UKLID - "Virtuální"
    zaskrtnute jen aby v adminu zmizelo nepotrebne pole Odečty, ne proto,
    ze by melo skutecny vzorec) nikdy nevrati zadnou hodnotu
    (_formula_consumption_for na prazdnem vzorci vzdy da None) - takove
    meridlo se tedy pocita stejne jako nevirtualni bez odectu.

    `cache`: volitelny dict {meter_id: bool} pro memoizaci napric
    volanimi v ramci jednoho vypoctu (calculate_period) - bez neho by
    se meter.readings.exists() (skutecny DB dotaz) volalo znovu pro
    KAZDY klic napojeny na tohle meridlo, i vickrat pro tentyz meridlo
    (jednou v has_meter_keys, znovu uvnitr _consumption_shares) - u
    polozky s desitkami klicu to delalo desitky zbytecnych dotazu
    navic. Viz konverzace s Danielem - vypocet za obdobi se z ~3s
    zpomalil na 1-2 min presne od chvile, co tahle funkce pribyla."""
    if cache is not None and meter.id in cache:
        return cache[meter.id]
    if meter.is_virtual:
        result = bool(meter.formula.strip())
    else:
        result = meter.readings.exists()
    if cache is not None:
        cache[meter.id] = result
    return result


def _fixed_amount_for(key, service_item, period, warnings, price_cache=None):
    """Vrati absolutni mesicni Kc castku pro klic typu FIXED_AMOUNT/AREA_PRICE,
    zkracenou podle POCTU AKTIVNICH DNI karty v obdobi.

    Kdyz platnost Karty/Smlouvy zacne (nebo skonci) uprostred mesice, plati
    klient jen pomernou cast - nastoupi-li 16. dne z 31, zaplati 16/31
    pausalu. Stejne pravidlo uz plati u vazenych podilu (_weighted_shares),
    do teto chvile se ale pausaly uctovaly vzdy cele. U pausalu s
    "Odečíst z celkového nákladu" se tim z poolu odecte mene, takze zbytek
    spravne pripadne ostatnim. Viz konverzace s Danielem 2026-08-17.

    `price_cache`: viz PriceList.get_price_for_period - predano dal beze zmeny."""
    if key.allocation_type == AllocationKey.AllocationType.AREA_PRICE:
        # Cena z klíče (individuálně sjednaná cena karty) má přednost před
        # Ceníkem položky; Ceník je implicitní default, když klíč cenu nemá.
        if key.unit_price is not None:
            price = key.unit_price
        else:
            price = PriceList.get_price_for_period(service_item, period, price_cache=price_cache)
        if price is None:
            warnings.append(
                f"{service_item}: klíč 'Plocha × cena/m²' pro kartu {key.client_card} "
                f"nemá cenu ani na klíči, ani v Ceníku pro toto ani žádné dřívější "
                f"období - karta vynechána."
            )
            return None
        zaklad = (key.value or Decimal("0")) * price / 12
    else:
        zaklad = key.value or Decimal("0")
    return _kraceno_dny(zaklad, key.client_card, period)


def _kraceno_dny(castka, card, period):
    """Zkrati castku pomerem aktivnich dni karty k delce obdobi. Karta
    platna cely mesic dostane castku beze zmeny (vc. presneho zaokrouhleni),
    takze na dosavadnich datech se nic nemeni."""
    period_start, period_end = period.date_range()
    active_days = card.active_days_in_period(period_start, period_end)
    dnu = period.days_in_period
    if active_days >= dnu:
        return castka.quantize(Decimal("0.01"))
    if active_days <= 0:
        return Decimal("0")
    return (castka * Decimal(active_days) / Decimal(dnu)).quantize(Decimal("0.01"))


def _weighted_shares(keys, period, by_key_out=None):
    """
    Spocita normalizovane podily (soucet = 1) pro seznam klicu typu
    "Podle váhy" (WEIGHTED_COUNT, vaha = AllocationKey.value - libovolne
    relativni cislo, m2/pocet osob/kusy/cokoliv) - nebo klicu typu
    "Podružné měřidlo" (SUBMETER) pri lokalnim deleni jednoho konkretniho
    meridla mezi vice karet, ktere ho sdili (viz _consumption_shares) -
    tam ma value stejny vyznam (vaha pro rozdeleni). V obou pripadech se
    prihlizi k aktivnim dnum karty v obdobi.

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


def _owned_consumption(meter, period, billed_meter_ids, cache, readings_cache=None, warnings=None):
    """Vrati "vlastni" spotrebu meridla za obdobi - jeho surovy odecet minus
    spotreba prime podrizenych meridel (Meter.parent_meter/children), ktera
    jsou SAMA O SOBE take samostatne uctovana (meter.id je v
    billed_meter_ids - typicky maji vlastni klic na stejne polozce, napr.
    E_AB1_10 je master k E_AB1_11/E_AB1_12, kazde s vlastni kartou). Bez
    tohoto odectu by se spotreba podrizenych meridel zapocitala dvakrat -
    jednou pod sebou, jednou uz zahrnuta v surovem odectu nadrazeneho
    meridla. Podrizena meridla BEZ vlastniho klice na teto polozce se
    neodecitaji - jejich spotreba spravne zustava soucasti nadrazeneho.

    `readings_cache`: viz Meter.consumption_for - predano dal beze zmeny.

    DULEZITE: odecita se SUROVA spotreba primeho ditete
    (child.consumption_for), NE jeho uz zredukovana "vlastni" hodnota
    (rekurzivni _owned_consumption(child)). U vicevrstve hierarchie
    (napr. meridlo -> dite -> vnouce, vsechny s vlastnim klicem na
    stejne polozce) by odectenim uz zredukovane hodnoty ditete zustala
    cast spotreby vnoucete "schovana" uvnitr nejvyssiho meridla (bylo
    by odecteno min, nez ma byt) - matematicky overeno (teleskopicky
    soucet), ze SUROVE odecitani na kazde urovni zvlast je spravne pro
    libovolnou hloubku hierarchie. Viz konverzace s Danielem 2026-08-12
    (stejna oprava jako v core/admin.py report_spotreby_view)."""
    if meter.id in cache:
        return cache[meter.id]
    raw = meter.consumption_for(period, readings_cache=readings_cache)
    if raw is None:
        cache[meter.id] = None
        return None
    deduction = Decimal("0")
    for child in meter.children.all():
        if child.id in billed_meter_ids:
            child_consumption = child.consumption_for(period, readings_cache=readings_cache)
            if child_consumption is not None:
                deduction += child_consumption
    result = raw - deduction
    if result < 0:
        # Podruzna meridla namerila vic nez nadrazene - fyzikalne nemozne,
        # v praxi proměření / ruzne dny odectu / vadne meridlo. Zaporna
        # spotreba by dala klientovi zaporny podil (dobropis), proto se
        # orezava na nulu; rozdil se rozpusti do celku, protoze se
        # rozdeluje NAKLAD v Kc, ne kWh. Hlasi se, aby chyba mereni
        # nezustala schovana. Viz konverzace s Danielem 2026-08-17.
        if warnings is not None:
            deti = ", ".join(
                c.code or c.name for c in meter.children.all() if c.id in billed_meter_ids
            )
            warnings.append(
                f"{meter.code or meter.name}: podružná měřidla ({deti}) naměřila o "
                f"{-result} víc než nadřazené měřidlo - vlastní spotřeba oříznuta na 0. "
                f"Zkontroluj odečty."
            )
        result = Decimal("0")
    cache[meter.id] = result
    return result


def _consumption_shares(
    service_item, period, warnings, by_key_out=None, by_key_local_out=None, by_meter_out=None,
    meter_provides_cache=None, readings_cache=None,
):
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

    `by_key_local_out`: volitelny dict {allocation_key_id: Decimal podil},
    do ktereho se navic zapise LOKALNI podil klice v ramci SVE SKUPINY
    (stejneho meridla) - u meridla, ktere pouziva jen jedna karta, je to
    vzdy 1 (100 %); u sdileneho meridla je to jeho vaha normalizovana jen
    proti ostatnim kartam na TOMTO meridle. Slouzi jen k auditu ("mam
    spravne rozdelene sdilene meridlo?"), na skutecny vypocet nema vliv.

    `by_meter_out`: volitelny dict {meter_id: {"meter", "consumption",
    "contribution", "cards"}}, jen pro auditovaci rozpad po MERIDLECH
    (ne po klicich/kartach) - viz billing/item_summary.py, prehled
    Naklad/Vynos s rozpadem na meridla. Bez vlivu na vysledek ani
    chovani, pokud zustane None.

    `meter_provides_cache`: volitelny dict predany do
    _meter_provides_consumption - memoizuje "ma tohle meridlo skutecna
    data" napric VICE volanimi (calculate_period predava jeden sdileny
    cache pro cely vypocet obdobi), aby se meter.readings.exists() pro
    stejne meridlo nevolalo znovu a znovu. Bez vlivu na vysledek, jen
    na pocet DB dotazu.

    `readings_cache`: viz Meter.consumption_for - volitelny dict
    hromadne predem nactenych odectu, predava se dal do
    main_meter.consumption_for a _owned_consumption. Bez vlivu na
    vysledek, jen na pocet DB dotazu.
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
        if key.meter_id is not None and _meter_provides_consumption(key.meter, cache=meter_provides_cache):
            keys_by_meter.setdefault(key.meter_id, []).append(key)
        else:
            weight_keys.append(key)

    main_meter = service_item.meter
    if main_meter is not None:
        total_consumption = main_meter.consumption_for(period, readings_cache=readings_cache)
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
    owned_consumption_cache = {}

    for meter_id, group_keys in keys_by_meter.items():
        group_meter = group_keys[0].meter
        group_consumption = _owned_consumption(
            group_meter, period, keys_by_meter.keys(), owned_consumption_cache,
            readings_cache=readings_cache, warnings=warnings,
        )
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

    for meter_id, (group_consumption, group_keys) in resolved_groups.items():
        contribution = group_consumption / total_consumption

        if by_meter_out is not None:
            by_meter_out[meter_id] = {
                "meter": group_keys[0].meter,
                "consumption": group_consumption,
                "contribution": contribution,
                "cards": [str(k.client_card) for k in group_keys],
            }

        if len(group_keys) == 1:
            key = group_keys[0]
            shares[key.client_card_id] = shares.get(key.client_card_id, Decimal("0")) + contribution
            if by_key_out is not None:
                by_key_out[key.id] = contribution
            if by_key_local_out is not None:
                by_key_local_out[key.id] = Decimal("1")
        else:
            need_local = by_key_out is not None or by_key_local_out is not None
            local_by_key = {} if need_local else None
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
            if by_key_local_out is not None:
                for key_id, weight in local_by_key.items():
                    by_key_local_out[key_id] = weight

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


def surcharge_split(share, units, remaining_cost, reported_units, total_consumption):
    """Rozpad spotrebni casti castky na "vlastni spotreba" a "spolecne
    prostory + ztraty" - JEN pro zobrazeni, na vypocet nema zadny vliv.

    Klient plati sve namerene jednotky, jenze cena za jednotku, kterou
    vidi ve vyuctovani (total_cost / namerena spotreba), je vyssi nez ta
    fakturovana dodavatelem (naklad / fakturovane mnozstvi) - do rozdilu
    je schovane vsechno, co dodavatel naúctoval navic proti souctu
    podmeru: osvetleni spolecnych prostor, technicke ztraty, nezachycene
    odbery. Bez rozpadu to ve vyuctovani vypada jako 5,20 Kc/kWh proti
    4,80 Kc/kWh na fakture, aniz by z ceho koli slo poznat proc.
    Viz konverzace s Danielem 2026-08-15.

    Rozpad (vse odvozene z uz spocitanych hodnot, nic se nepocita znovu):
      cena bez priplatku = zbyla castka / fakturovane mnozstvi
      vlastni spotreba   = jednotky karty x cena bez priplatku
      priplatek          = zbyla castka x podil - vlastni spotreba
    Priplatek se dopocitava jako zbytek (ne nezavislym zaokrouhlenim),
    aby soucet obou radku dal presne fakturovanou castku.

    Vraci dict, nebo None kdyz rozpad nedava smysl (polozka bez
    fakturovaneho mnozstvi - typicky nemerena sluzba uctovana v Kc, nebo
    karta bez podilu na spotrebe).
    """
    if not reported_units or reported_units <= 0 or not total_consumption:
        return None
    if share is None or units is None or remaining_cost is None:
        return None
    base_price_per_unit = (remaining_cost / reported_units).quantize(Decimal("0.0001"))
    own_amount = (units * base_price_per_unit).quantize(Decimal("0.01"))
    share_amount = (remaining_cost * share).quantize(Decimal("0.01"))
    return {
        "reported_units": reported_units,
        "base_price_per_unit": base_price_per_unit,
        "own_amount": own_amount,
        "surcharge_units": (share * (reported_units - total_consumption)).quantize(Decimal("0.001")),
        "surcharge_amount": share_amount - own_amount,
    }


def sync_card_activity(period, site=None):
    """Pred vypoctem rozuctovani automaticky zkontroluje a opravi
    ClientCard.is_active podle Platnost od/do vuci pocitanemu obdobi -
    aby se pri prechodu na novou kartu (renovace najmu) nemuselo rucne
    pamatovat na prepnuti Aktivni/Neaktivni presne v tu spravnou chvili
    (viz konverzace s Danielem - is_active nema zadny casovy rozmer sam
    o sobe, calculate_period ho bere jako plosne "tahle karta ted
    plati", bez ohledu na to, jake obdobi se zrovna pocita).

    Dve kategorie zmen, ruzne bezpecne:
    - DEAKTIVACE (Platnost do uz pred timto obdobim, ale porad
      Aktivni): vzdy jednoznacna a bezpecna, provede se automaticky.
    - AKTIVACE (Platnost od uz zacala, ale karta je Neaktivni): provede
      se automaticky JEN pokud tim nevznikne konflikt (jina aktivni
      karta stejneho klienta ve stejnem arealu) - jinak zustane
      needotcena a jen se nahlasi jako varovani, at si to Daniel
      zkontroluje rucne (typicky rozpracovana/koncept karta, kterou
      jeste nechce pustit do ostreho provozu).

    Vraci list (level, text) zprav pro zobrazeni v adminu - level je
    "success" (deaktivovano/aktivovano) nebo "warning" (konflikt)."""
    period_start, period_end = period.date_range()

    cards = ClientCard.objects.select_related("client").prefetch_related("card_units__unit__site")
    if site is not None:
        cards = cards.filter(card_units__unit__site=site).distinct()
    else:
        cards = cards.distinct()

    results = []

    to_deactivate = [c for c in cards if c.is_active and c.valid_to and c.valid_to < period_start]
    for card in to_deactivate:
        card.is_active = False
        card.save(update_fields=["is_active"])
        results.append(("success", f"{card.client} ({card}): automaticky DEAKTIVOVÁNO (platnost do {card.valid_to})"))

    to_check = [
        c for c in cards
        if not c.is_active and c.valid_from <= period_end and (not c.valid_to or c.valid_to >= period_start)
    ]
    for card in to_check:
        conflict = card.active_card_conflict()
        if conflict is None:
            card.is_active = True
            card.save(update_fields=["is_active"])
            results.append(("success", f"{card.client} ({card}): automaticky AKTIVOVÁNO (platnost od {card.valid_from})"))
        else:
            results.append((
                "warning",
                f"{card.client} ({card}): platnost od {card.valid_from} už začala, ale je Neaktivní - "
                f"NEaktivováno automaticky, protože koliduje s aktivní kartou {conflict} - zkontroluj ručně."
            ))

    return results


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
    to_create = []

    with transaction.atomic():
        billing_lines = BillingLine.objects.filter(period=period)
        service_items = ServicePoolItem.objects.select_related("meter", "site")
        if site is not None:
            billing_lines = billing_lines.filter(service_item__site=site)
            service_items = service_items.filter(site=site)
        billing_lines.delete()

        # Vsechny Naklady za tohle obdobi nactene JEDNOU dopredu (misto
        # dotazu na CostEntry pro kazdou polozku zvlast, ~90 dotazu jen
        # na tohle) - viz konverzace s Danielem, vypocet za obdobi byl
        # strasne pomaly.
        # Polozka muze mit vic faktur od ruznych dodavatelu (elektrina FM =
        # TEDOM + SZYPKA, teplo NJ = pelety + zalozni elektrokotel), proto
        # SEZNAM, ne jeden zaznam - rozuctuje se jejich soucet, viz
        # CostEntry.totals_for.
        cost_entries_by_item = {}
        for ce in CostEntry.objects.filter(period=period):
            cost_entries_by_item.setdefault(ce.service_item_id, []).append(ce)

        # Sdileny cache pro _meter_provides_consumption napric CELYM
        # vypoctem obdobi (vsechny polozky) - viz docstring te funkce.
        meter_provides_cache = {}

        # Hromadne predem nactene odecty pro AKTUALNI a PREDCHOZI obdobi
        # (jedinym dotazem) - misto toho, aby si kazde meridlo (a u
        # formulovych/virtualnich meridel kazda jeho slozka) tahalo svuj
        # odecet samostatnym dotazem znovu a znovu. U arealu s velkym
        # poctem meridel (napr. tisice prostoru) je tohle klicove pro
        # skalovatelnost - bez toho roste pocet DB dotazu linearne s
        # poctem meridel, misto aby zustal konstantni (2 dotazy celkem).
        # Viz Meter.consumption_for.
        prev_period = period.previous_period()
        relevant_periods = [period] + ([prev_period] if prev_period else [])
        readings_cache = {
            (r.meter_id, r.period_id): r
            for r in MeterReading.objects.filter(period__in=relevant_periods)
        }

        # Hromadne predem nactene ceniky vsech polozek (jedinym dotazem) -
        # "posledni platna cena k datu" se pak dohleda v pameti (viz
        # PriceList.get_price_for_period) misto samostatneho dotazu na
        # KAZDOU polozku s merenym nakladem a KAZDY klic typu
        # "Plocha × cena/m²". Stejny vzor jako u readings_cache vyse.
        price_cache = {}
        for pl in (
            PriceList.objects.filter(service_item__in=service_items)
            .select_related("period")
            .order_by("service_item_id", "-period__year", "-period__month")
        ):
            price_cache.setdefault(pl.service_item_id, []).append(pl)

        # Prepinac "odecitat pausaly z celkoveho nakladu" po Tridach
        # (Nastavení -> Třídy) - nactene jednou pro cely vypocet.
        deduct_fixed_by_class = InvoiceClassColor.deduct_fixed_map()

        for service_item in service_items:
            deduct_fixed_allowed = deduct_fixed_by_class.get(service_item.invoice_class, True)
            item_costs = cost_entries_by_item.get(service_item.id) or []
            cost_entry = item_costs[0] if item_costs else None
            cost_totals = CostEntry.totals_for(
                service_item, period, price_cache=price_cache, entries=item_costs,
            )
            cost_source = None
            if item_costs:
                total_cost = cost_totals["czk"]
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
                amount = _fixed_amount_for(key, service_item, period, warnings, price_cache=price_cache)
                if amount is None:
                    continue
                fixed_amounts[key.client_card_id] = fixed_amounts.get(key.client_card_id, Decimal("0")) + amount
                if key.allocation_type == AllocationKey.AllocationType.AREA_PRICE:
                    # Cena z klíče (sjednaná cena karty) má přednost před Ceníkem
                    # - stejně jako v _fixed_amount_for.
                    if key.unit_price is not None:
                        price = key.unit_price
                    else:
                        price = PriceList.get_price_for_period(service_item, period, price_cache=price_cache)
                    if price is not None:
                        fixed_units[key.client_card_id] = (
                            fixed_units.get(key.client_card_id, Decimal("0")) + (key.value or Decimal("0"))
                        )
                        fixed_price_per_unit[key.client_card_id] = price
                # Odecist lze jen kdyz to dovoli TRIDA i klic - prepinac
                # v Nastavení -> Třídy umi vypnout odecitani pausalu plosne
                # (pak se cely naklad deli mezi ostatni, jako to delal stary
                # system), jednotlivy klic ho muze vypnout i nad ramec toho.
                # Viz InvoiceClassColor.deduct_fixed_from_pool.
                if key.deduct_from_pool and deduct_fixed_allowed:
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
                k.meter_id is not None and _meter_provides_consumption(k.meter, cache=meter_provides_cache)
                for k in valid_keys if k.allocation_type not in ABSOLUTE_AMOUNT_TYPES
            )
            if service_item.meter or has_meter_keys:
                shares, total_consumption = _consumption_shares(
                    service_item, period, warnings,
                    meter_provides_cache=meter_provides_cache, readings_cache=readings_cache,
                )
            else:
                weight_keys = [
                    k for k in valid_keys if k.allocation_type not in ABSOLUTE_AMOUNT_TYPES
                ]
                shares = _weighted_shares(weight_keys, period)
                # Hlásit "nerozpočítaná zbylá částka" jen když položku fakticky
                # NIKDO neplatí - tj. nejsou ani vážené/měřené podíly, ani žádné
                # pevné částky. U položek účtovaných čistě pevnou cenou (napr.
                # srážkové vody: plocha × cena, deduct=False) zbývá zaznamenaný
                # náklad "nerozpočítaný" schválně (rozdíl nese pronajímatel),
                # klienti platí své pevné částky - to není chyba. Naopak položka
                # bez jakýchkoli klíčů (napr. nově přidaný servis výtahů) hlásí
                # dál. Viz konverzace s Danielem.
                if not shares and remaining_cost != 0 and not fixed_amounts:
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
                split = None
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

                    # Rozpad "vlastni spotreba" vs "spolecne + ztraty" - jen
                    # informativni, uklada se do calc_detail, aby ho slo ukazat
                    # v klientskem vyuctovani i po uzavreni obdobi (PDF cte
                    # vyhradne ulozene hodnoty, nikdy neprepocitava). Viz
                    # surcharge_split.
                    split = surcharge_split(
                        share, units, remaining_cost,
                        cost_totals["units"], total_consumption,
                    )

                to_create.append(BillingLine(
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
                        **({
                            "reported_units": str(split["reported_units"]),
                            "base_price_per_unit": str(split["base_price_per_unit"]),
                            "own_amount": str(split["own_amount"]),
                            "surcharge_units": str(split["surcharge_units"]),
                            "surcharge_amount": str(split["surcharge_amount"]),
                        } if split else {}),
                    },
                ))

        # Jeden hromadny INSERT na konci mista jednoho radku po druhem -
        # u vypoctu s desitkami polozek x desitkami klientu to drive
        # znamenalo stovky samostatnych DB zapisu. Viz konverzace
        # s Danielem - "vypocet za obdobi strasne dlouho trva".
        BillingLine.objects.bulk_create(to_create)

    return {"created": len(to_create), "warnings": warnings}
