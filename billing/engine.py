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
"""
from decimal import Decimal

from django.db import transaction

from core.models import AllocationKey, BillingLine, CostEntry, ServicePoolItem


def _weighted_shares(keys, period):
    """
    Spocita normalizovane podily (soucet = 1) pro seznam klicu
    typu percent / area_ratio / person_count / equal_split,
    s prihlednutim k aktivnim dnum karty v obdobi.

    Vraci dict {client_card_id: Decimal podil}.
    """
    period_start, period_end = period.date_range()
    days_in_period = Decimal(period.days_in_period)

    raw_weights = {}
    for key in keys:
        card = key.client_card
        active_days = card.active_days_in_period(period_start, period_end)
        if active_days <= 0:
            continue

        if key.allocation_type == AllocationKey.AllocationType.AREA_RATIO:
            base = card.unit.area_m2 or Decimal("0")
        elif key.allocation_type == AllocationKey.AllocationType.PERSON_COUNT:
            base = key.value or Decimal("0")
        elif key.allocation_type == AllocationKey.AllocationType.EQUAL_SPLIT:
            base = Decimal("1")
        else:  # PERCENT
            base = key.value or Decimal("0")

        effective_weight = base * (Decimal(active_days) / days_in_period)
        raw_weights[card.id] = raw_weights.get(card.id, Decimal("0")) + effective_weight

    total = sum(raw_weights.values())
    if total == 0:
        return {}
    return {card_id: weight / total for card_id, weight in raw_weights.items()}


def _consumption_shares(service_item, period, warnings):
    """
    Spocita podily pro merenou polozku (service_item.meter neni None).

    Vraci dict {client_card_id: Decimal podil}, soucet ~= 1, pokud
    se podarilo dohledat vsechny potrebne odecty. Pri chybejicich
    odectech pripoji varovani a vrati prazdny dict (polozka se
    pro toto obdobi vynecha).
    """
    meter = service_item.meter
    total_consumption = meter.consumption_for(period)
    if total_consumption is None:
        warnings.append(
            f"{service_item}: chybí odečet měřidla {meter} pro období {period} "
            f"nebo předchozí období - položka vynechána."
        )
        return {}
    if total_consumption == 0:
        warnings.append(f"{service_item}: nulová spotřeba měřidla {meter} - položka vynechána.")
        return {}

    keys = [
        k for k in service_item.allocation_keys.select_related("client_card", "client_card__unit", "meter")
        if k.is_valid_for_period(period) and k.allocation_type != AllocationKey.AllocationType.FIXED_AMOUNT
    ]

    submeter_keys = [k for k in keys if k.allocation_type == AllocationKey.AllocationType.SUBMETER]
    weight_keys = [k for k in keys if k.allocation_type != AllocationKey.AllocationType.SUBMETER]

    shares = {}
    sum_submeters = Decimal("0")
    for key in submeter_keys:
        if key.meter_id is None:
            warnings.append(
                f"{service_item}: klíč typu 'Podružné měřidlo' pro kartu {key.client_card} "
                f"(AllocationKey #{key.id}) nemá nastavené měřidlo - tato karta vynechána. "
                f"Buď doplň měřidlo u klíče, nebo změň typ klíče, pokud nemělo být 'submeter'."
            )
            continue
        sub_consumption = key.meter.consumption_for(period)
        if sub_consumption is None:
            warnings.append(
                f"{service_item}: chybí odečet podružného měřidla {key.meter} "
                f"pro kartu {key.client_card} - tato karta vynechána."
            )
            continue
        shares[key.client_card_id] = shares.get(key.client_card_id, Decimal("0")) + (
            sub_consumption / total_consumption
        )
        sum_submeters += sub_consumption

    residual = total_consumption - sum_submeters
    residual_fraction = residual / total_consumption

    if weight_keys and residual_fraction > 0:
        weight_shares = _weighted_shares(weight_keys, period)
        for card_id, weight in weight_shares.items():
            shares[card_id] = shares.get(card_id, Decimal("0")) + weight * residual_fraction
    elif residual_fraction != 0 and not weight_keys:
        warnings.append(
            f"{service_item}: zbývá {residual_fraction:.2%} spotřeby (společná část), "
            f"ale žádná karta nemá klíč pro její rozpočítání."
        )

    return shares


def calculate_period(period):
    """
    Spocita rozuctovani vsech polozek Zasobniku pro dane obdobi
    a ulozi vysledky do BillingLine (existujici radky pro toto
    obdobi se nahradi).

    Vraci dict se souhrnem: {"created": int, "warnings": [str, ...]}.
    """
    warnings = []
    created = 0

    with transaction.atomic():
        BillingLine.objects.filter(period=period).delete()

        for service_item in ServicePoolItem.objects.select_related("meter"):
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

            fixed_keys = [k for k in valid_keys if k.allocation_type == AllocationKey.AllocationType.FIXED_AMOUNT]

            # 1) pevne castky - odecist z celkove castky
            remaining_cost = total_cost
            fixed_amounts = {}
            for key in fixed_keys:
                amount = key.value or Decimal("0")
                fixed_amounts[key.client_card_id] = fixed_amounts.get(key.client_card_id, Decimal("0")) + amount
                remaining_cost -= amount

            if remaining_cost < 0:
                warnings.append(
                    f"{service_item} / {period}: pevné částky ({total_cost - remaining_cost} Kč) "
                    f"překračují celkový náklad ({total_cost} Kč)."
                )

            # 2) podily na zbytku castky
            if service_item.meter:
                shares = _consumption_shares(service_item, period, warnings)
            else:
                weight_keys = [
                    k for k in valid_keys if k.allocation_type != AllocationKey.AllocationType.FIXED_AMOUNT
                ]
                shares = _weighted_shares(weight_keys, period)
                if not shares and remaining_cost != 0:
                    warnings.append(f"{service_item} / {period}: žádné klíče pro rozpočítání zbylé částky.")

            # 3) sestaveni vysledku
            results = dict(fixed_amounts)
            for card_id, share in shares.items():
                results[card_id] = results.get(card_id, Decimal("0")) + remaining_cost * share

            for card_id, amount in results.items():
                share = shares.get(card_id)
                BillingLine.objects.create(
                    client_card_id=card_id,
                    period=period,
                    service_item=service_item,
                    amount=amount.quantize(Decimal("0.01")),
                    share=share,
                    calc_detail={
                        "total_cost": str(total_cost),
                        "cost_source": cost_source,
                        "fixed_amount": str(fixed_amounts.get(card_id, Decimal("0"))),
                        "remaining_cost": str(remaining_cost),
                        "share": str(share) if share is not None else None,
                    },
                )
                created += 1

    return {"created": created, "warnings": warnings}
