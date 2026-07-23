"""
Generovani klientskeho vyuctovani (PDF).

Ukazuje, jak se doslo k celkove fakturaci za jednotlive tridy zasobniku
(najemne/elektrina/voda/teplo/ostatni) - rozpad na jednotlive polozky
zasobniku uvnitr kazde tridy, sectene napric vsemi kartami klienta pro
dane obdobi (BillingLine).

Font: pouziva se DejaVu Sans, bundlovany v billing/fonts/ (volne siritelny,
stejna licence jako Bitstream Vera). Reportlab sice ma vlastni vestaveny
font Vera, ten ale ma vadny/chybejici glyf pro "ě"/"Ě" (U+011B/U+011A) -
v cestine caste znaky, ktere by se jinak v generovanych PDF tise vykreslily
jako prazdny ctverecek. Overeno primym testem (canvas.drawString), DejaVu
Sans tento problem nema.
"""
import os
from decimal import Decimal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from core.models import BillingLine, ServicePoolItem

_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(_FONT_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")))

_CLASS_ORDER = [code for code, _ in ServicePoolItem.InvoiceClass.choices]

_STYLE_TITLE = ParagraphStyle("StatementTitle", fontName="DejaVu-Bold", fontSize=16, spaceAfter=4 * mm)
_STYLE_SUB = ParagraphStyle("StatementSub", fontName="DejaVu", fontSize=11, spaceAfter=6 * mm, leading=15)
_STYLE_H2 = ParagraphStyle("StatementH2", fontName="DejaVu-Bold", fontSize=13, spaceBefore=6 * mm, spaceAfter=2 * mm)
_STYLE_TOTAL = ParagraphStyle("StatementTotal", fontName="DejaVu-Bold", fontSize=13, spaceBefore=8 * mm)
_STYLE_EMPTY = ParagraphStyle("StatementEmpty", fontName="DejaVu", fontSize=10, spaceBefore=4 * mm)


def _card_label(card):
    return card.description or f"Karta {card.client}"


def _fmt_czk(amount):
    if amount is None:
        return "—"
    return f"{amount:,.2f} Kč".replace(",", " ")


def build_statement_data(client, period):
    """Sestaví data vyúčtování klienta za období napříč všemi jeho kartami.
    Vrací dict: {"classes": [{"label", "lines": [...], "subtotal"}], "grand_total"}."""
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
                {"item": line.service_item.name, "card": _card_label(line.client_card), "amount": line.amount}
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

        headers = ["Položka"] + (["Karta"] if show_card_column else []) + ["Částka (Kč)"]
        rows = [headers]
        for line in cls["lines"]:
            row = [line["item"]]
            if show_card_column:
                row.append(line["card"])
            row.append(_fmt_czk(line["amount"]))
            rows.append(row)
        rows.append(["Mezisoučet"] + ([""] if show_card_column else []) + [_fmt_czk(cls["subtotal"])])

        table = Table(rows, repeatRows=1)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
            ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "DejaVu-Bold"),
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
