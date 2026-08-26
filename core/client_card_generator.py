"""
Generovani dokumentu Karty najemce (PDF) - Priloha c. 1 ke Smlouve.

Cernobile, bezpatkove (PT Sans Narrow - viz core/pdf_fonts.py, vizualne
blizky Arial Narrow, kterym je psana samotna Smlouva), maly font (~8pt),
tabulky zarovnane doleva a bez mezer mezi radky - vzhled odpovida
poznamkovemu prehledu k podpisu, ne reprezentativnimu dokumentu.
Klient/Karta/Platnost od jsou vyrazeny tucne a o neco vetsim pismem
nez zbytek.
"""
from decimal import ROUND_CEILING, Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from django.db.models import F

from core.contract_generator import format_date_cz, get_landlord
from core.models import AllocationKey, InvoiceClassColor, ServicePoolItem
from core.pdf_fonts import FONT_CARD_BOLD as FONT_BOLD
from core.pdf_fonts import FONT_CARD_REGULAR as FONT_REGULAR

_FONT_SIZE = 8


class _NumberedCanvas(_canvas.Canvas):
    """Canvas, ktery na konci kazdou stranku doplni o cislovani "Strana X z Y" -
    celkovy pocet stran neni znamy, dokud nejsou vsechny vysazene, proto se
    stranky nejdriv jen bufferuji (showPage) a fyzicky vykresli az v save()."""

    def __init__(self, *args, **kwargs):
        _canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(total_pages)
            _canvas.Canvas.showPage(self)
        _canvas.Canvas.save(self)

    def _draw_page_number(self, total_pages):
        self.setFont(FONT_REGULAR, _FONT_SIZE)
        self.drawCentredString(
            A4[0] / 2, 10 * mm, f"Stránka {self._pageNumber} z {total_pages}"
        )


_STYLE_HEADER = ParagraphStyle("CardHeader", fontName=FONT_BOLD, fontSize=_FONT_SIZE, alignment=2)  # 2 = right
_STYLE_INFO = ParagraphStyle("CardInfo", fontName=FONT_BOLD, fontSize=_FONT_SIZE + 2, leading=_FONT_SIZE + 5)
_STYLE_H2 = ParagraphStyle("CardH2", fontName=FONT_BOLD, fontSize=_FONT_SIZE + 1, spaceBefore=4 * mm, spaceAfter=1 * mm)
_STYLE_SIG_LABEL = ParagraphStyle("CardSigLabel", fontName=FONT_BOLD, fontSize=_FONT_SIZE, alignment=1)  # 1 = center
_STYLE_SIG_LINE = ParagraphStyle("CardSigLine", fontName=FONT_REGULAR, fontSize=_FONT_SIZE, alignment=1)
_STYLE_SIG_NAME = ParagraphStyle("CardSigName", fontName=FONT_REGULAR, fontSize=_FONT_SIZE, alignment=1)
_SIG_GAP = 3 * _FONT_SIZE * 1.2  # >= 3 blank lines between "Pronajímatel/Nájemce" heading and the signature line

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


def _strip_trailing_zeros(value):
    """Ustripuje nadbytecne nuly z Decimalu bez rizika vedecke notace, na
    rozdil od Decimal.normalize() (napr. Decimal('140.0000').normalize()
    da '1.4E+2' - nechteny format pro zobrazeni klientovi)."""
    text = f"{value:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _fmt_key_value(key):
    """Hodnota klíče formátovaná podle typu výpočtu - měna jen tam, kam patří."""
    if key.value is None:
        return "—"
    t = AllocationKey.AllocationType
    value = _strip_trailing_zeros(key.value)
    if key.allocation_type == t.AREA_PRICE:
        return f"{value} m²"
    if key.allocation_type == t.FIXED_AMOUNT:
        return _fmt_kc(key.value)
    if key.allocation_type == t.SUBMETER:
        return "—"
    if key.allocation_type == t.WEIGHTED_COUNT and key.weight_unit_label:
        return f"{value} ({key.weight_unit_label})"
    return f"{value}"


_STYLE_PLAN_POPIS = ParagraphStyle(
    "CardPlanPopis", fontName=FONT_REGULAR, fontSize=_FONT_SIZE, leading=_FONT_SIZE + 3,
)


def _planek_stranky(card, sirka, vyska):
    """Stranky s pudorysy pater, na kterych ma Karta plochy.

    Vraci flowables k pripojeni na konec dokumentu - kazdy planek zacina na
    nove strane. Kdyz planek chybi, nejde precist nebo neni nainstalovana
    svglib, vrati se prazdny seznam a Karta se vygeneruje jako driv; priloha
    je hezka navic, ne duvod, proc by nemela jit vytisknout smlouva.
    """
    from io import BytesIO

    try:
        from svglib.svglib import svg2rlg
    except ImportError:
        return []

    from core.floorplan import oznac_plochy_pro_tisk, planky_pro_kartu

    out = []
    for plan, moje in planky_pro_kartu(card):
        try:
            svg = oznac_plochy_pro_tisk(plan.read_svg(), moje)
            kresba = svg2rlg(BytesIO(svg.encode("utf-8")))
        except Exception:
            continue
        if kresba is None or not kresba.width or not kresba.height:
            continue

        pomer = min(sirka / kresba.width, vyska / kresba.height)
        kresba.width *= pomer
        kresba.height *= pomer
        kresba.scale(pomer, pomer)
        kresba.hAlign = "CENTER"

        out.append(PageBreak())
        out.append(Paragraph(f"Plánek – {plan.name}", _STYLE_H2))
        out.append(Paragraph(
            "Tmavě zvýrazněné jsou plochy této Karty ({}). Ostatní plochy jsou "
            "světlé, jen pro orientaci v patře.".format(", ".join(moje)),
            _STYLE_PLAN_POPIS,
        ))
        out.append(Spacer(1, 3 * mm))
        out.append(kresba)
    return out


def generate_client_card_document(card, output_path):
    """Vygeneruje Kartu nájemce (Příloha č. 1) pro danou ClientCard jako PDF
    a uloží do output_path (cesta nebo zapisovatelný stream, např. BytesIO)."""
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )
    elements = [Paragraph("Příloha č. 1 ke Smlouvě o nájmu", _STYLE_HEADER), Spacer(1, 4 * mm)]

    info_lines = [
        f"Klient: {card.client}",
        f"Karta: {card.description or f'Karta {card.client}'}",
        f"Platnost od: {format_date_cz(card.valid_from)}",
    ]
    if card.valid_to:
        info_lines.append(f"Platnost do: {format_date_cz(card.valid_to)}")
    elements.append(Paragraph("<br/>".join(info_lines), _STYLE_INFO))

    # --- Plochy ---
    elements.append(Paragraph("Pronajaté plochy", _STYLE_H2))
    rows = [["Plocha", "Výměra", "Cena (Kč/m²/rok)", "Nájemné/rok", "Nájemné/měsíc"]]

    total_area = Decimal("0")
    total_year = Decimal("0")
    total_month = Decimal("0")
    for cu in card.card_units.select_related("unit__site"):
        area = cu.area_m2
        # cu.monthly_rent uz sjednanou pevnou castku resi (prebiji sazbu),
        # takze se z nej odvozuje i rocni najem - jinak by karta u takove
        # plochy tiskla prazdno. Viz Daniel 2026-08-17.
        month_rent = cu.monthly_rent
        year_rent = (month_rent * 12) if month_rent is not None else None

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

    units_table = Table(rows, repeatRows=1, hAlign="LEFT")
    units_table.setStyle(TableStyle([
        *_TABLE_BASE_STYLE,
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTNAME", (0, -1), (-1, -1), FONT_BOLD),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]))
    elements.append(units_table)

    # --- Klíče - jedna souvislá tabulka, třídy oddělené silnější linkou ---
    elements.append(Paragraph("Klíče rozúčtování služeb", _STYLE_H2))
    # Stejne razeni jako sekce Klicu v adminu (core.admin
    # AllocationKeyInlineBase.get_queryset): v ramci Polozky zasobniku
    # jeste podle Podruzneho meridla, klic bez meridla prvni - at Karta
    # v PDF sedi s tim, co je videt ve formulari. Daniel 2026-08-26.
    #
    # nulls_first se pise vyslovne: Postgres radi prazdne hodnoty pri
    # vzestupnem razeni na KONEC, sqlite na zacatek.
    keys = list(
        card.allocation_keys
        .select_related("service_item", "meter")
        .order_by(
            "service_item__invoice_class", "service_item__name",
            F("meter__code").asc(nulls_first=True), "pk",
        )
    )
    # Poradi i nazvy Trid se berou z DB (Nastaveni -> Tridy) az za behu -
    # na urovni modulu by to byl dotaz uz pri importu (pada pri migrate).
    class_labels = InvoiceClassColor.label_map()
    class_order = [code for code, _ in InvoiceClassColor.choices()]

    key_rows = [["Položka", "Měřidlo", "Typ výpočtu", "Hodnota", "Fakturovat"]]
    type_labels = dict(AllocationKey.AllocationType.choices)
    class_header_rows = []  # indexy radku s nazvem tridy - pro silnejsi linku/tucne pismo

    for class_code in class_order:
        class_keys = [k for k in keys if k.service_item.invoice_class == class_code]
        if not class_keys:
            continue
        class_header_rows.append(len(key_rows))
        key_rows.append([class_labels[class_code], "", "", "", ""])
        for key in class_keys:
            key_rows.append([
                key.service_item.name,
                str(key.meter) if key.meter else "—",
                type_labels.get(key.allocation_type, key.allocation_type),
                _fmt_key_value(key),
                "Ano" if key.is_billed else "V paušálu",
            ])

    keys_style = [
        *_TABLE_BASE_STYLE,
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
    ]
    for row_idx in class_header_rows:
        keys_style.append(("SPAN", (0, row_idx), (-1, row_idx)))
        keys_style.append(("FONTNAME", (0, row_idx), (-1, row_idx), FONT_BOLD))
        keys_style.append(("LINEABOVE", (0, row_idx), (-1, row_idx), 1.2, colors.black))

    if len(key_rows) > 1:
        keys_table = Table(key_rows, repeatRows=1, hAlign="LEFT")
        keys_table.setStyle(TableStyle(keys_style))
        elements.append(keys_table)

    # --- Podpisy: datum podpisu / nadpis strany / čára / jméno zástupce pod čarou ---
    elements.append(Spacer(1, 10 * mm))
    elements.append(Paragraph(f"Datum podpisu: {format_date_cz(card.signed_on)}", _STYLE_H2))
    sig_rows = [
        [Paragraph("Pronajímatel", _STYLE_SIG_LABEL), Paragraph("Nájemce", _STYLE_SIG_LABEL)],
        [Paragraph("_" * 35, _STYLE_SIG_LINE), Paragraph("_" * 35, _STYLE_SIG_LINE)],
        [Paragraph(get_landlord(card.site).representative_name, _STYLE_SIG_NAME),
         Paragraph(str(card.client), _STYLE_SIG_NAME)],
    ]
    sig_table = Table(sig_rows, colWidths=[85 * mm, 85 * mm], hAlign="LEFT")
    sig_table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 1), (-1, 1), _SIG_GAP),
    ]))
    elements.append(sig_table)

    # --- Plánky pater, kde má karta plochy (každý na vlastní straně) ---
    elements.extend(_planek_stranky(card, doc.width, doc.height - 20 * mm))

    doc.build(elements, canvasmaker=_NumberedCanvas)
    return output_path
