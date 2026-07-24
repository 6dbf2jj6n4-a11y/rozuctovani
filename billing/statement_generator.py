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

from core.models import BillingLine, ServicePoolItem
from core.pdf_fonts import FONT_BOLD, FONT_REGULAR

_CLASS_ORDER = [code for code, _ in ServicePoolItem.InvoiceClass.choices]

_STYLE_TITLE = ParagraphStyle("StatementTitle", fontName=FONT_BOLD, fontSize=16, spaceAfter=4 * mm)
_STYLE_SUB = ParagraphStyle("StatementSub", fontName=FONT_REGULAR, fontSize=11, spaceAfter=6 * mm, leading=15)
_STYLE_H2 = ParagraphStyle("StatementH2", fontName=FONT_BOLD, fontSize=13, spaceBefore=6 * mm, spaceAfter=2 * mm)
_STYLE_TOTAL = ParagraphStyle("StatementTotal", fontName=FONT_BOLD, fontSize=13, spaceBefore=8 * mm)
_STYLE_EMPTY = ParagraphStyle("StatementEmpty", fontName=FONT_REGULAR, fontSize=10, spaceBefore=4 * mm)


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


def format_price_per_unit(price, unit_of_measure):
    """Cena za jednotku, např. '10.00 Kč/kWh'. U m² jde vždy o roční sazbu
    (Kč/m²/rok) - stejná konvence jako v core/client_card_generator.py."""
    if price is None:
        return "—"
    label = "m²/rok" if unit_of_measure == "m²" else (unit_of_measure or "j.")
    return f"{price:,.2f} Kč/{label}".replace(",", " ")


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
        .order_by("service_item__invoice_class", "service_item__name")
    )
    class_labels = dict(ServicePoolItem.InvoiceClass.choices)

    classes = []
    grand_total = Decimal("0")
    for class_code in _CLASS_ORDER:
        class_lines = [line for line in lines if line.service_item.invoice_class == class_code]
        if not class_lines:
            continue
        subtotal = sum((line.amount for line in class_lines), Decimal("0"))
        classes.append({
            "label": class_labels[class_code],
            "lines": [
                {
                    "item": line.service_item.name,
                    "card": _card_label(line.client_card),
                    "amount": line.amount,
                    "units": line.units,
                    "unit_of_measure": line.calc_detail.get("unit_of_measure"),
                    "price_per_unit": (
                        Decimal(line.calc_detail["price_per_unit"])
                        if line.calc_detail.get("price_per_unit") else None
                    ),
                }
                for line in class_lines
            ],
            "subtotal": subtotal,
        })
        grand_total += subtotal

    return {"classes": classes, "grand_total": grand_total}


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
        for line in cls["lines"]:
            row = [line["item"]]
            if show_card_column:
                row.append(line["card"])
            row.append(format_units(line["units"], line["unit_of_measure"]))
            row.append(format_price_per_unit(line["price_per_unit"], line["unit_of_measure"]))
            row.append(_fmt_czk(line["amount"]))
            rows.append(row)
        filler = [""] * (2 + (1 if show_card_column else 0))
        rows.append(["Mezisoučet"] + filler + [_fmt_czk(cls["subtotal"])])

        table = Table(rows, repeatRows=1)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("FONTNAME", (0, -1), (-1, -1), FONT_BOLD),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f3f4f6")),
            ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9ca3af")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(table)

    elements.append(Paragraph(f"Celkem k úhradě: {_fmt_czk(data['grand_total'])}", _STYLE_TOTAL))

    doc.build(elements)
    return output_path
