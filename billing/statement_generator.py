"""
Generovani klientskeho vyuctovani (PDF).

Ukazuje, jak se doslo k celkove fakturaci za jednotlive tridy zasobniku
(najemne/elektrina/voda/teplo/ostatni) - rozpad na jednotlive polozky
zasobniku uvnitr kazde tridy, sectene napric vsemi kartami klienta pro
dane obdobi (BillingLine).

Font: viz core/pdf_fonts.py (DejaVu Sans - reportlab vestaveny font Vera
ma vadny glyf pro "ě"/"Ě").
"""
from decimal import Decimal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from core.models import BillingLine, InvoiceClassColor, ServicePoolItem
from core.pdf_fonts import FONT_BOLD, FONT_REGULAR


_STYLE_TITLE = ParagraphStyle("StatementTitle", fontName=FONT_BOLD, fontSize=16, spaceAfter=4 * mm)
_STYLE_SUB = ParagraphStyle("StatementSub", fontName=FONT_REGULAR, fontSize=11, spaceAfter=6 * mm, leading=15)
_STYLE_H2 = ParagraphStyle("StatementH2", fontName=FONT_BOLD, fontSize=13, spaceBefore=6 * mm, spaceAfter=2 * mm)
_STYLE_TOTAL = ParagraphStyle("StatementTotal", fontName=FONT_BOLD, fontSize=13, spaceBefore=8 * mm)
_STYLE_EMPTY = ParagraphStyle("StatementEmpty", fontName=FONT_REGULAR, fontSize=10, spaceBefore=4 * mm)


_STYLE_METER = ParagraphStyle(
    "StatementMeter", fontName=FONT_REGULAR, fontSize=8, leading=10,
    textColor=colors.HexColor("#6b7280"), leftIndent=10,
)
_STYLE_BASIS = ParagraphStyle(
    "StatementBasis", fontName=FONT_REGULAR, fontSize=8, leading=11,
    spaceBefore=2 * mm, spaceAfter=3 * mm, textColor=colors.HexColor("#4b5563"),
)


def _cislo(hodnota, mist=3):
    """Stav nebo spotreba meridla bez zbytecnych nul: 292 350, 0.952.
    Koeficient se tiskne s `mist=6` - teplo ma 0,0036 a zaokrouhlene
    0,004 by klientovi nesedelo s tim, co si prepocita."""
    d = Decimal(str(hodnota))
    if d == d.to_integral_value():
        return f"{d:,.0f}".replace(",", " ")
    return f"{d:,.{mist}f}".rstrip("0").rstrip(".").replace(",", " ")


def meridlo_text(radek):
    """Popis jednoho meridla v rozpadu polozky - z ceho se jednotky karty
    skladaji, aby si je klient overil na svem meridle. Radky pripravuje
    billing/engine.py _rozpad_po_meridlech a ukladaji se pri vypoctu.
    Viz Daniel 2026-09-25: "klient musi videt spotrebu na meridlech"."""
    mj = radek.get("mj") or ""
    if radek.get("spolecne"):
        return "podíl na nezměřené společné spotřebě"
    kod = radek.get("kod") or ""
    if radek.get("virtualni"):
        text = f"{kod} – společná spotřeba {_cislo(radek['spotreba'])} {mj}"
    elif radek.get("stav_akt") is not None and radek.get("stav_pred") is not None:
        text = f"{kod}: stav {_cislo(radek['stav_pred'])} → {_cislo(radek['stav_akt'])}"
        if radek.get("koeficient"):
            text += f" × koef. {_cislo(radek['koeficient'], mist=6)}"
        if radek.get("odecteno") and radek.get("namereno") is not None:
            text += f" = {_cislo(radek['namereno'])} {mj}"
    else:
        text = f"{kod}: spotřeba {_cislo(radek.get('namereno') or radek['spotreba'])} {mj}"
    for dite in radek.get("odecteno") or []:
        text += f", − {dite['kod']} {_cislo(dite['spotreba'])} {mj} (účtuje se zvlášť)"
    podil = Decimal(radek["podil"]) if radek.get("podil") else None
    if podil is not None and podil != 1:
        if not radek.get("virtualni") and not radek.get("odecteno"):
            text += f" = {_cislo(radek['spotreba'])} {mj}"
        # nezlomitelna mezera - "%" nesmi pri zalomeni zustat samo na radku
        text += f", váš podíl {podil * 100:.2f}\u00a0%"
    return text.strip()


def poznamka_k_rozpadu(s_vyrovnanim):
    """Poznamka pod carou k radkum "z toho". Veta o vyrovnani rozdilu
    mereni jen tehdy, kdyz nejaky takovy radek ve vyuctovani je - se
    zapnutym prepinacem kladnych ztrat se namereny prebytek klientum
    nevraci a veta by lhala."""
    text = (
        "Řádky „z toho“ jsou jen rozpis částky nad nimi, nepřičítají se k ní. "
        "Cena za jednotku v tomto vyúčtování se liší od ceny na faktuře dodavatele "
        "proto, že celý fakturovaný náklad dělíme spotřebou skutečně naměřenou "
        "podružnými měřidly. Naměří-li se méně, než dodavatel fakturoval, je "
        "v rozdílu spotřeba společných prostor a ztráty v rozvodech a dělí se mezi "
        "odběratele v poměru jejich naměřené spotřeby."
    )
    if s_vyrovnanim:
        text += " Naměří-li se více, vrací se rozdíl odběratelům jako vyrovnání rozdílu měření."
    return text


def price_basis_text(zaklad):
    """Odkud se vzala cena za jednotku, po řádcích - aby si ji klient mohl
    ověřit proti faktuře dodavatele, kterou zná, a nedopočítával si
    zákonnou ztrátu podruhé. Stejný text v PDF i v klientském portálu,
    proto bez značkování. Viz Daniel 2026-09-16."""
    mj = zaklad["unit_of_measure"] or "j."
    if zaklad.get("jen_faktura"):
        # Klient plati namerene jednotky x cenu z faktury - staci ukazat
        # fakturu. Viz billing/engine.py (prepinac kladnych ztrat).
        radky = [
            f"Cena dle faktury dodavatele: {_fmt_czk(zaklad['cost'])} "
            f"za {format_units(zaklad['reported_units'], mj)} = "
            f"{format_price_per_unit(zaklad['base_price_per_unit'], mj, decimals=4)}"
        ]
        if zaklad["legal_loss_pct"]:
            pct = f"{zaklad['legal_loss_pct']:.2f}".rstrip("0").rstrip(".")
            radky.append(
                f"Fakturované množství už obsahuje zákonnou ztrátu {pct} %, kterou "
                f"dodavatel připočítává - samostatně se neúčtuje."
            )
        return radky
    radky = [
        f"Náklad dle faktury dodavatele: {_fmt_czk(zaklad['cost'])} "
        f"za {format_units(zaklad['reported_units'], mj)} = "
        f"{format_price_per_unit(zaklad['base_price_per_unit'], mj, decimals=4)}"
    ]
    if zaklad["legal_loss_pct"]:
        pct = f"{zaklad['legal_loss_pct']:.2f}".rstrip("0").rstrip(".")
        radky.append(
            f"Fakturované množství už obsahuje zákonnou ztrátu {pct} %, kterou "
            f"dodavatel připočítává - samostatně se neúčtuje."
        )
    if zaklad["measured_units"] is not None and zaklad["difference_units"] is not None:
        rozdil = zaklad["difference_units"]
        smer = "více" if rozdil > 0 else "méně"
        pct = zaklad["difference_pct"]
        pct_text = f", {pct:+.1f} %" if pct is not None else ""
        radky.append(
            f"Součet spotřeb naměřených v areálu: "
            f"{format_units(zaklad['measured_units'], mj)} "
            f"(o {format_units(abs(rozdil), mj)} {smer}{pct_text})"
        )
        radky.append(
            f"Rozúčtovací cena: {_fmt_czk(zaklad['cost'])} ÷ "
            f"{format_units(zaklad['measured_units'], mj)} = "
            f"{format_price_per_unit(zaklad['price_per_unit'], mj, decimals=4)}"
        )
    return radky


def _card_label(card):
    return card.description or f"Karta {card.client}"


def _fmt_czk(amount):
    if amount is None:
        return "—"
    return f"{amount:,.2f} Kč".replace(",", " ")


def format_units(units, unit_of_measure):
    """Spotřeba/výměra u položky, např. '500.00 kWh' - '—' pokud položka
    žádnou fyzikální jednotku nemá (paušál, procentní klíč apod.)."""
    if units is None:
        return "—"
    label = unit_of_measure or ""
    return f"{units:,.2f} {label}".replace(",", " ").strip()


def format_price_per_unit(price, unit_of_measure, decimals=2):
    """Cena za jednotku, např. '10.00 Kč/kWh'. U m² jde vždy o roční sazbu
    (Kč/m²/rok) - stejná konvence jako v core/client_card_generator.py.

    `decimals`: v odvození ceny se tiskne na 4 místa - klient si má umět
    svou částku ověřit vynásobením, a při 6.47 Kč/kWh místo 6.4651 mu
    vyjde o procento jiné číslo. Viz Daniel 2026-09-16."""
    if price is None:
        return "—"
    label = "m²/rok" if unit_of_measure == "m²" else (unit_of_measure or "j.")
    return f"{price:,.{decimals}f} Kč/{label}".replace(",", " ")


def surcharge_label(surcharge_amount):
    """Popisek rozpadoveho radku podle znamenka rozdilu - viz
    billing/engine.py surcharge_split. Kladny rozdil klient doplaci
    (spolecne prostory a ztraty), zaporny dostava zpatky (namerili jsme
    vic, nez dodavatel fakturoval). Jedno jmeno pro oba smery by lhalo
    v jednom z nich. Viz Daniel 2026-09-16."""
    if surcharge_amount is None:
        return ""
    if surcharge_amount < 0:
        return "z toho vyrovnání rozdílu měření"
    return "z toho společné prostory a ztráty"


def build_statement_data(client, period):
    """Sestaví data vyúčtování klienta za období napříč všemi jeho kartami.
    Vrací dict: {"classes": [{"label", "lines": [...], "subtotal"}], "grand_total"}.
    Každý řádek obsahuje i units/unit_of_measure/price_per_unit (může být None
    u položek bez fyzikální jednotky, např. paušál nebo procentní klíč) -
    hodnoty se čtou z BillingLine.units a calc_detail uložených při výpočtu
    (billing/engine.py), nikdy se nedopočítávají znovu."""
    lines = (
        BillingLine.objects
        .filter(period=period, client_card__client=client)
        .select_related("service_item", "client_card")
        .order_by("service_item__invoice_class", "service_item__name", "-is_billed")
    )
    # Karta s pausalem a nefakturovanym skutecnym podilem na te same
    # polozce ma dva radky (billing/engine.py, 3) sestaveni) - popisek
    # rekne, ktery je k uhrade a ktery jen pro informaci.
    _pocet = {}
    for line in lines:
        _pocet[(line.client_card_id, line.service_item_id)] = _pocet.get(
            (line.client_card_id, line.service_item_id), 0) + 1

    def _nazev(line):
        if _pocet[(line.client_card_id, line.service_item_id)] < 2:
            return line.service_item.name
        if not line.is_billed:
            return f"{line.service_item.name} – skutečná spotřeba"
        if line.share is None:
            return f"{line.service_item.name} – paušál"
        return line.service_item.name

    # Poradi i nazvy Trid z DB az za behu - viz client_card_generator.
    class_labels = InvoiceClassColor.label_map()
    class_order = [code for code, _ in InvoiceClassColor.choices()]

    def _dec(calc_detail, field):
        raw = calc_detail.get(field)
        return Decimal(raw) if raw is not None else None

    def _cena_odvozena(class_lines):
        """Odvozeni ceny za jednotku pro tridu - jeden zaznam za kazdou
        polozku zasobniku, ktera se delila podle namerene spotreby.
        Klient musi videt obe cisla: cenu z faktury dodavatele (tu si
        umi overit na dokladu) i rozuctovaci cenu (tou nasobime jeho
        kWh). Vsechno se cte z calc_detail ulozeneho pri vypoctu."""
        zaznamy = []
        videno = set()
        for line in class_lines:
            cd = line.calc_detail or {}
            fa = cd.get("cena_z_faktury")
            if fa and line.service_item_id not in videno:
                # Prepinac kladnych ztrat: jen skutecna faktura, zadna
                # namerena mnozstvi (prozradila by prebytek pronajimatele).
                videno.add(line.service_item_id)
                zaznam = {
                    "item": line.service_item.name,
                    "unit_of_measure": cd.get("unit_of_measure") or "",
                    "jen_faktura": True,
                    "cost": Decimal(fa["naklad"]),
                    "reported_units": Decimal(fa["mnozstvi"]),
                    "base_price_per_unit": Decimal(fa["cena"]),
                    "legal_loss_pct": Decimal(fa["legal_loss_pct"]) if fa.get("legal_loss_pct") else None,
                }
                zaznam["text"] = price_basis_text(zaznam)
                zaznamy.append(zaznam)
                continue
            if not cd.get("reported_units") or not cd.get("base_price_per_unit"):
                continue
            if line.service_item_id in videno:
                continue
            videno.add(line.service_item_id)
            fakturovano = Decimal(cd["reported_units"])
            namereno = _dec(cd, "measured_units")
            rozdil = (namereno - fakturovano) if namereno is not None else None
            zaznamy.append({
                "item": line.service_item.name,
                "unit_of_measure": cd.get("unit_of_measure") or "",
                "cost": _dec(cd, "remaining_cost"),
                "reported_units": fakturovano,
                "base_price_per_unit": _dec(cd, "base_price_per_unit"),
                "measured_units": namereno,
                "difference_units": rozdil,
                "difference_pct": (
                    (rozdil / fakturovano * 100).quantize(Decimal("0.1"))
                    if rozdil is not None and fakturovano else None
                ),
                "price_per_unit": _dec(cd, "price_per_unit"),
                "legal_loss_pct": _dec(cd, "legal_loss_pct"),
            })
        for zaznam in zaznamy:
            zaznam["text"] = price_basis_text(zaznam)
        return zaznamy

    classes = []
    grand_total = Decimal("0")
    any_unbilled = False
    any_surcharge = False
    any_vyrovnani = False
    for class_code in class_order:
        class_lines = [line for line in lines if line.service_item.invoice_class == class_code]
        if not class_lines:
            continue
        # Mezisoucet (a celkova castka k uhrade) zahrnuje jen fakturovane
        # radky - polozky s is_billed=False se zobrazuji jen informativne
        # (klient uz je ma zahrnute v pausalu), viz AllocationKey.is_billed.
        subtotal = sum((line.amount for line in class_lines if line.is_billed), Decimal("0"))
        if any(not line.is_billed for line in class_lines):
            any_unbilled = True
        if any(line.calc_detail.get("surcharge_amount") for line in class_lines):
            any_surcharge = True
        if any(Decimal(line.calc_detail["surcharge_amount"]) < 0
               for line in class_lines if line.calc_detail.get("surcharge_amount")):
            any_vyrovnani = True
        classes.append({
            "label": class_labels[class_code],
            "price_basis": _cena_odvozena(class_lines),
            "lines": [
                {
                    "item": _nazev(line),
                    "card": _card_label(line.client_card),
                    "amount": line.amount,
                    "is_billed": line.is_billed,
                    "units": line.units,
                    "unit_of_measure": line.calc_detail.get("unit_of_measure"),
                    "price_per_unit": (
                        Decimal(line.calc_detail["price_per_unit"])
                        if line.calc_detail.get("price_per_unit") else None
                    ),
                    # Rozpad castky na vlastni namerenou spotrebu a priplatek
                    # za spolecne prostory + ztraty (viz billing/engine.py
                    # surcharge_split). U starsich obdobi, spocitanych jeste
                    # pred zavedenim rozpadu, tahle pole v calc_detail nejsou -
                    # zustanou None a v PDF se proste neukazou.
                    "base_price_per_unit": _dec(line.calc_detail, "base_price_per_unit"),
                    "own_amount": _dec(line.calc_detail, "own_amount"),
                    "surcharge_units": _dec(line.calc_detail, "surcharge_units"),
                    "surcharge_amount": _dec(line.calc_detail, "surcharge_amount"),
                    "surcharge_label": surcharge_label(
                        _dec(line.calc_detail, "surcharge_amount")),
                    # Rozpad po meridlech (billing/engine.py
                    # _rozpad_po_meridlech). Obdobi spocitana pred jeho
                    # zavedenim ho v calc_detail nemaji - pak se proste
                    # neukaze.
                    "meridla": [
                        {
                            "text": meridlo_text(r),
                            "units": Decimal(r["jednotky"]) if r.get("jednotky") else None,
                            "unit_of_measure": r.get("mj") or line.calc_detail.get("unit_of_measure"),
                            "units_text": format_units(
                                Decimal(r["jednotky"]) if r.get("jednotky") else None,
                                r.get("mj") or line.calc_detail.get("unit_of_measure"),
                            ),
                        }
                        for r in (line.calc_detail or {}).get("meridla", [])
                    ],
                }
                for line in class_lines
            ],
            "subtotal": subtotal,
        })
        grand_total += subtotal

    return {
        "classes": classes, "grand_total": grand_total,
        "any_unbilled": any_unbilled, "any_surcharge": any_surcharge,
        "any_vyrovnani": any_vyrovnani,
    }


def generate_client_statement_pdf(client, period, output_path):
    """Vygeneruje PDF vyúčtování a uloží do output_path (cesta nebo
    zapisovatelný stream, např. BytesIO)."""
    data = build_statement_data(client, period)
    all_cards = {line["card"] for cls in data["classes"] for line in cls["lines"]}
    show_card_column = len(all_cards) > 1

    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    elements = [
        Paragraph("Vyúčtování", _STYLE_TITLE),
        Paragraph(f"Klient: {escape(client.name)}<br/>Období: {escape(str(period))}", _STYLE_SUB),
    ]

    if not data["classes"]:
        elements.append(Paragraph(
            "Pro toto období nejsou k dispozici žádné vyúčtované položky.", _STYLE_EMPTY
        ))

    for cls in data["classes"]:
        elements.append(Paragraph(escape(cls["label"]), _STYLE_H2))

        headers = (
            ["Položka"] + (["Karta"] if show_card_column else [])
            + ["Spotřeba", "Cena/jednotku", "Částka (Kč)"]
        )
        rows = [headers]
        # Radky rozpadu (vlastni spotreba / spolecne + ztraty) jsou jen
        # vysvetlujici - do mezisouctu nevstupuji, proto se tisknou mensim
        # sedym pismem, aby nevypadaly jako dalsi uctovana polozka.
        detail_row_indexes = []
        for line in cls["lines"]:
            row = [line["item"]]
            if show_card_column:
                row.append(line["card"])
            row.append(format_units(line["units"], line["unit_of_measure"]))
            row.append(format_price_per_unit(line["price_per_unit"], line["unit_of_measure"]))
            amount_text = _fmt_czk(line["amount"])
            if not line["is_billed"]:
                amount_text += " (v paušálu)"
            row.append(amount_text)
            rows.append(row)

            for meridlo in line["meridla"]:
                detail_row_indexes.append(len(rows))
                sub_row = [Paragraph(escape(meridlo["text"]), _STYLE_METER)]
                if show_card_column:
                    sub_row.append("")
                sub_row.append(format_units(meridlo["units"], meridlo["unit_of_measure"]))
                sub_row.append("")
                sub_row.append("")
                rows.append(sub_row)

            if line["surcharge_amount"]:
                breakdown = (
                    ("z toho vlastní naměřená spotřeba", line["units"], line["own_amount"]),
                    (line["surcharge_label"], line["surcharge_units"], line["surcharge_amount"]),
                )
                for label, sub_units, sub_amount in breakdown:
                    detail_row_indexes.append(len(rows))
                    sub_row = [f"     {label}"]
                    if show_card_column:
                        sub_row.append("")
                    sub_row.append(format_units(sub_units, line["unit_of_measure"]))
                    sub_row.append(
                        format_price_per_unit(line["base_price_per_unit"], line["unit_of_measure"])
                    )
                    sub_row.append(_fmt_czk(sub_amount))
                    rows.append(sub_row)

        filler = [""] * (2 + (1 if show_card_column else 0))
        rows.append(["Mezisoučet"] + filler + [_fmt_czk(cls["subtotal"])])

        # Vsechny tabulky na celou sirku stranky se stejnymi sloupci - jinak
        # si kazda pocita sirku podle obsahu a pravé okraje trid pod sebou
        # nelicuji (Ostatni byla uzsi). Ciselne sloupce (Spotreba,
        # Cena/jednotku, Castka) jsou zarovnane doprava, i v zahlavi.
        # Viz Daniel 2026-09-25.
        ciselne = [26 * mm, 30 * mm, 30 * mm]
        karta = [30 * mm] if show_card_column else []
        prvni_ciselny = 1 + len(karta)
        sirky = [doc.width - sum(ciselne) - sum(karta)] + karta + ciselne
        table = Table(rows, repeatRows=1, colWidths=sirky)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("FONTNAME", (0, -1), (-1, -1), FONT_BOLD),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f3f4f6")),
            ("ALIGN", (prvni_ciselny, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9ca3af")),
            # Zalomeny popis meridla je vyssi nez jeden radek - jednotky
            # a castky at stoji nahore u zacatku textu, ne u jeho konce.
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            # Az na konci - pravidla pro cely rozsah tabulky vyse by je
            # jinak prepsala (reportlab aplikuje prikazy v poradi).
            *[
                style
                for i in detail_row_indexes
                for style in (
                    ("TEXTCOLOR", (0, i), (-1, i), colors.HexColor("#6b7280")),
                    ("FONTSIZE", (0, i), (-1, i), 8),
                )
            ],
        ]))
        elements.append(table)
        for zaklad in cls["price_basis"]:
            elements.append(Paragraph(
                "<br/>".join([f"<b>Jak jsme došli k ceně – {escape(zaklad['item'])}</b>"]
                             + [escape(radek) for radek in zaklad["text"]]),
                _STYLE_BASIS,
            ))

    elements.append(Paragraph(f"Celkem k úhradě: {_fmt_czk(data['grand_total'])}", _STYLE_TOTAL))
    if data["any_unbilled"]:
        elements.append(Paragraph(
            "Položky označené „(v paušálu)“ jsou v tomto výpisu jen pro přehlednost - "
            "máte je již zahrnuté v paušální platbě, proto nejsou v částce k úhradě.",
            _STYLE_EMPTY,
        ))
    if data["any_surcharge"]:
        elements.append(Paragraph(poznamka_k_rozpadu(data["any_vyrovnani"]), _STYLE_EMPTY))

    doc.build(elements)
    return output_path
