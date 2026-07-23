"""
Generovani dokumentu Karty najemce (PDF) - Priloha c. 1 ke Smlouve.

Cernobile, bezpatkove (DejaVu Sans - viz core/pdf_fonts.py), maly font
(~10pt), kompaktni tabulky bez mezer mezi radky - vzhled odpovida
poznamkovemu prehledu k podpisu, ne reprezentativnimu dokumentu.
"""
import math
from decimal import ROUND_CEILING, Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.contract_generator import LANDLORD_REPRESENTATIVE, format_date_cz
from core.models import AllocationKey, ServicePoolItem
from core.pdf_fonts import FONT_BOLD, FONT_REGULAR

_CLASS_ORDER = [code for code, _ in ServicePoolItem.InvoiceClass.choices]
_FONT_SIZE = 10

_STYLE_HEADER = ParagraphStyle("CardHeader", fontName=FONT_BOLD, fontSize=_FONT_SIZE, alignment=2)  # 2 = right
_STYLE_INFO = ParagraphStyle("CardInfo", fontName=FONT_REGULAR, fontSize=_FONT_SIZE, leading=13)
_STYLE_H2 = ParagraphStyle("CardH2", fontName=FONT_BOLD, fontSize=_FONT_SIZE + 1, spaceBefore=4 * mm, spaceAfter=1 * mm)
_STYLE_SIG = ParagraphStyle("CardSig", fontName=FONT_REGULAR, fontSize=_FONT_SIZE)

_TABLE_BASE_STYLE = [
    ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
    ("FONTSIZE", (0, 0), (-1, -1), _FONT_SIZE),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
    ("TOPPADDING", (0, 0), (-1, -1), 1),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
]


def _fmt_m2(value):
    if value is None:
        return "—"
    return f"{value:.2f} m²"


def _fmt_kc(value, whole=False):
    if value is None:
        return "—"
    if whole:
        value = value.to_integral_value(rounding=ROUND_CEILING)
        return f"{int(value):,} Kč".replace(",", " ")
    return f"{value:,.2f} Kč".replace(",", " ")


def _fmt_key_value(key):
    """Hodnota klíče formátovaná podle typu výpočtu - měna jen tam, kam patří."""
    if key.value is None:
        return "—"
    t = AllocationKey.AllocationType
    value = key.value.normalize()
    if key.allocation_type == t.PERCENT:
        return f"{value} %"
    if key.allocation_type == t.PERSON_COUNT:
        return f"{value} osob"
    if key.allocation_type in (t.AREA_RATIO, t.AREA_PRICE):
        return f"{value} m²"
    if key.allocation_type == t.FIXED_AMOUNT:
        return _fmt_kc(key.value)
    if key.allocation_type in (t.EQUAL_SPLIT, t.SUBMETER):
        return "—"
    return f"{value}"


def generate_client_card_document(card, output_path):
    """Vygeneruje Kartu nájemce (Příloha č. 1) pro danou ClientCard jako PDF
    a uloží do output_path (cesta nebo zapisovatelný stream, např. BytesIO)."""
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )
    elements = [Paragraph("Příloha č. 1", _STYLE_HEADER), Spacer(1, 4 * mm)]

    info_lines = [
        f"<b>Klient:</b> {card.client}",
        f"<b>Karta:</b> {card.description or f'Karta {card.client}'}",
        f"<b>Platnost od:</b> {format_date_cz(card.valid_from)}",
    ]
    if card.valid_to:
        info_lines.append(f"<b>Platnost do:</b> {format_date_cz(card.valid_to)}")
    elements.append(Paragraph("<br/>".join(info_lines), _STYLE_INFO))

    # --- Plochy ---
    elements.append(Paragraph("Pronajaté plochy", _STYLE_H2))
    rows = [["Plocha", "Výměra", "Cena (Kč/m²/rok)", "Nájemné/rok", "Nájemné/měsíc"]]

    total_area = Decimal("0")
    total_year = Decimal("0")
    total_month = Decimal("0")
    for cu in card.card_units.select_related("unit__site"):
        area = cu.area_m2
        year_rent = (area * cu.rate_per_m2) if (area and cu.rate_per_m2) else None
        month_rent = (year_rent / 12) if year_rent is not None else None

        rows.append([
            str(cu.unit) if cu.unit else "—",
            _fmt_m2(area),
            _fmt_kc(cu.rate_per_m2),
            _fmt_kc(year_rent, whole=True),
            _fmt_kc(month_rent, whole=True),
        ])

        total_area += area or Decimal("0")
        total_year += year_rent or Decimal("0")
        total_month += month_rent or Decimal("0")

    rows.append([
        "Celkem", _fmt_m2(total_area), "",
        _fmt_kc(total_year, whole=True), _fmt_kc(total_month, whole=True),
    ])

    units_table = Table(rows, repeatRows=1)
    units_table.setStyle(TableStyle([
        *_TABLE_BASE_STYLE,
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTNAME", (0, -1), (-1, -1), FONT_BOLD),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]))
    elements.append(units_table)

    # --- Klíče - jedna souvislá tabulka, třídy oddělené silnější linkou ---
    elements.append(Paragraph("Klíče rozúčtování služeb", _STYLE_H2))
    keys = list(
        card.allocation_keys
        .select_related("service_item", "meter")
        .order_by("service_item__invoice_class", "service_item__name")
    )
    class_labels = dict(ServicePoolItem.InvoiceClass.choices)

    key_rows = [["Položka", "Měřidlo", "Typ výpočtu", "Hodnota"]]
    type_labels = dict(AllocationKey.AllocationType.choices)
    class_header_rows = []  # indexy radku s nazvem tridy - pro silnejsi linku/tucne pismo

    for class_code in _CLASS_ORDER:
        class_keys = [k for k in keys if k.service_item.invoice_class == class_code]
        if not class_keys:
            continue
        class_header_rows.append(len(key_rows))
        key_rows.append([class_labels[class_code], "", "", ""])
        for key in class_keys:
            key_rows.append([
                key.service_item.name,
                str(key.meter) if key.meter else "—",
                type_labels.get(key.allocation_type, key.allocation_type),
                _fmt_key_value(key),
            ])

    keys_style = [
        *_TABLE_BASE_STYLE,
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
    ]
    for row_idx in class_header_rows:
        keys_style.append(("SPAN", (0, row_idx), (-1, row_idx)))
        keys_style.append(("FONTNAME", (0, row_idx), (-1, row_idx), FONT_BOLD))
        keys_style.append(("LINEABOVE", (0, row_idx), (-1, row_idx), 1.2, colors.black))

    if len(key_rows) > 1:
        keys_table = Table(key_rows, repeatRows=1)
        keys_table.setStyle(TableStyle(keys_style))
        elements.append(keys_table)

    # --- Podpisy ---
    elements.append(Spacer(1, 10 * mm))
    elements.append(Paragraph("_" * 30 + "&nbsp;" * 15 + "_" * 30, _STYLE_SIG))
    elements.append(Paragraph(
        f"za Pronajímatele: {LANDLORD_REPRESENTATIVE}"
        + "&nbsp;" * 15 + f"za Nájemce: {card.client}",
        _STYLE_SIG,
    ))

    doc.build(elements)
    return output_path
