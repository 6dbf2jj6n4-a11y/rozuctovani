"""
Generovani dokumentu Karty najemce (PDF) - Priloha c. 1 ke Smlouve.

Cernobile, bezpatkove (PT Sans Narrow - viz core/pdf_fonts.py, vizualne
blizky Arial Narrow, kterym je psana samotna Smlouva), maly font (~8pt),
tabulky zarovnane doleva a bez mezer mezi radky - vzhled odpovida
poznamkovemu prehledu k podpisu, ne reprezentativnimu dokumentu.
Klient/Karta/Platnost od jsou vyrazeny tucne a o neco vetsim pismem
nez zbytek.
"""
import math
from decimal import ROUND_CEILING, Decimal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from django.db.models import F

from core.contract_generator import format_date_cz, get_landlord
from core.models import AllocationKey, InvoiceClassColor, Period, PriceList, ServicePoolItem
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
# Nazev Karty - nadpis hlavicky, vetsi nez udaje pod nim (Daniel 2026-09-29).
_STYLE_NAZEV_KARTY = ParagraphStyle(
    "CardNazev", fontName=FONT_BOLD, fontSize=_FONT_SIZE + 6, leading=_FONT_SIZE + 9,
)
# Krok tabulatoru jako ve Wordu (1,25 cm). Udaje v hlavicce zacinaji na
# nejblizsi zarazce za popiskem - "za dvojteckou odrazit jednim tabem".
_TAB = 12.5 * mm
_STYLE_H2 = ParagraphStyle("CardH2", fontName=FONT_BOLD, fontSize=_FONT_SIZE + 1, spaceBefore=4 * mm, spaceAfter=1 * mm)
# Nadpis hlavni sekce Karty (Pronajate plochy, Poskytovane sluzby) - podkres
# pres celou sirku, at jsou sekce na prvni pohled oddelene. Daniel 2026-10-15.
_STYLE_SEKCE = ParagraphStyle(
    "CardSekce", parent=_STYLE_H2, backColor=colors.HexColor("#e5e7eb"),
    borderPadding=(2, 3, 2, 3), spaceBefore=5 * mm, spaceAfter=2 * mm,
)
# Podnadpis uvnitr sekce (Poskytovane sluzby: a) / b)) - Daniel 2026-10-15.
_STYLE_H3 = ParagraphStyle("CardH3", fontName=FONT_BOLD, fontSize=_FONT_SIZE, spaceBefore=2.5 * mm, spaceAfter=1 * mm)
_STYLE_SIG_LABEL = ParagraphStyle("CardSigLabel", fontName=FONT_BOLD, fontSize=_FONT_SIZE, alignment=1)  # 1 = center
_STYLE_SIG_LINE = ParagraphStyle("CardSigLine", fontName=FONT_REGULAR, fontSize=_FONT_SIZE, alignment=1)
_STYLE_SIG_NAME = ParagraphStyle("CardSigName", fontName=FONT_REGULAR, fontSize=_FONT_SIZE, alignment=1)
# Poznamky pod tabulkami (DPH) - obycejne pismo, maly odstup od tabulky.
_STYLE_POZNAMKA = ParagraphStyle(
    "CardPoznamka", fontName=FONT_REGULAR, fontSize=_FONT_SIZE,
    leading=_FONT_SIZE + 3, spaceBefore=1.5 * mm,
)
# Misto na podpis mezi "Pronajimatel/Najemce" a carou - 3 radky byly malo
# (Daniel 2026-10-15), ted 6.
_SIG_GAP = 6 * _FONT_SIZE * 1.2

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


def _sdilena_meridla(keys):
    """Dvojice (položka, měřidlo), na kterých je karet víc než jedna.

    Jen tam má hodnota klíče význam váhy - viz _fmt_key_value. Zjišťuje
    se jedním dotazem pro všechny klíče karty najednou; počítají se jen
    aktivní karty, tedy kdo měřidlo sdílí dnes."""
    from django.db.models import Count

    meridla = [k.meter_id for k in keys if k.meter_id]
    if not meridla:
        return set()
    return set(
        AllocationKey.objects.filter(
            meter_id__in=meridla, client_card__is_active=True
        )
        .values("service_item_id", "meter_id")
        .annotate(karet=Count("client_card", distinct=True))
        .filter(karet__gt=1)
        .values_list("service_item_id", "meter_id")
    )


def _osob(pocet):
    """1 osoba, 2-4 osoby, 0 a 5+ osob."""
    n = int(pocet or 0)
    slovo = "osoba" if n == 1 else ("osoby" if 2 <= n <= 4 else "osob")
    return f"{n} {slovo}"


def _fmt_key_value(key, sdilene_meridlo=False):
    """Hodnota klíče formátovaná podle typu výpočtu - měna jen tam, kam patří.

    U typu "Podle váhy na měřidle" záleží na tom, jestli měřidlo někdo
    sdílí. Když je na něm karta SAMA, dostane celou jeho spotřebu a
    hodnota nic neurčuje - tiskne se pomlčka. Když ho sdílí víc karet,
    je hodnota VÁHA, kterou se spotřeba mezi ně dělí, a musí být vidět.

    Dřív se tiskla pomlčka vždy, což byl pozůstatek doby, kdy se ten typ
    jmenoval "Podružné měřidlo (1:1)". Po přejmenování na "Podle váhy na
    měřidle" to začalo skrývat váhy i tam, kde nesou celý výpočet - na
    kartě KJO EU vycházelo osm hodnot z deseti jako pomlčka.
    Daniel 2026-08-27."""
    if key.weight_source in (AllocationKey.ZdrojVahy.OSOBY, AllocationKey.ZdrojVahy.OSOBY_TUV):
        # Vaha z Poctu osob na Karte (Daniel 2026-09-25).
        return _osob(key.vaha)
    if key.weight_source:
        # Klic s dopoctenou vahou Hodnotu vyplnenou nema - v Karte se ukaze
        # to, cim se opravdu deli, tedy plocha (Daniel 2026-09-05).
        popis = ("vytápěné plochy" if key.weight_source == AllocationKey.ZdrojVahy.VYTAPENA
                 else "plochy")
        return f"{_strip_trailing_zeros(key.vaha)} m² {popis}"
    if key.value is None:
        return "—"
    t = AllocationKey.AllocationType
    value = _strip_trailing_zeros(key.value)
    if key.allocation_type == t.AREA_PRICE:
        return f"{value} m²"
    if key.allocation_type == t.FIXED_AMOUNT:
        return _fmt_kc(key.value)
    # Pomlcka jen kdyz klic MERIDLO MA a je na nem sam - tehdy dostane
    # celou jeho spotrebu a hodnota nic neurcuje. Klic typu "na meridle"
    # BEZ meridla je nesmyslna kombinace (stava se pri zakladani karty);
    # hodnota v nem funguje jako vaha, tak ji radeji ukazat, nez ji tise
    # schovat za pomlcku.
    if key.allocation_type == t.WEIGHTED_COUNT and key.meter_id and not sdilene_meridlo:
        return "—"
    if key.weight_unit_label:
        return f"{value} ({key.weight_unit_label})"
    return f"{value}"


_STYLE_PLAN_POPIS = ParagraphStyle(
    "CardPlanPopis", fontName=FONT_REGULAR, fontSize=_FONT_SIZE, leading=_FONT_SIZE + 3,
)


def _pausal_za_mesic(key, obdobi):
    """(popis vypoctu, Kc za mesic) pro klic typu Pevna castka / Dle vymery.

    Stejny vypocet jako billing/engine.py _fixed_amount_for, jen bez kraceni
    dny - Karta uvadi sjednanou mesicni castku, ne vyuctovani konkretniho
    mesice. Cena za m2 se bere z klice, jinak z Ceniku polozky platneho
    v aktualnim obdobi (pripadne posledniho drivejsiho)."""
    t = AllocationKey.AllocationType
    if key.allocation_type == t.FIXED_AMOUNT:
        return "pevná částka", key.value
    vymera = key.vaha or Decimal("0")
    cena = key.unit_price
    if cena is None and obdobi is not None:
        cena = PriceList.get_price_for_period(key.service_item, obdobi)
    if cena is None:
        return f"{_strip_trailing_zeros(vymera)} m² × cena dle Ceníku", None
    popis = f"{_strip_trailing_zeros(vymera)} m² × {_fmt_kc(cena)}/m²/rok"
    return popis, (vymera * cena / 12).quantize(Decimal("0.01"))


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


def _na_tab(sirka):
    """Sirka sloupce zaokrouhlena na zarazku tabulatoru - aspon 2 mm
    mezera za nejdelsim textem, pak skok na nejblizsi nasobek _TAB."""
    return math.ceil((sirka + 2 * mm) / _TAB) * _TAB


def najem_s_dph(card):
    """Pripocita se k najemnemu DPH? Ano, kdyz aspon jedna Plocha karty
    jde zdanit - obe strany platci a nejde o byt (CardUnit.najem_lze_zdanit).
    Tiskne se v hlavicce Karty a urcuje poznamku pod Pronajatymi plochami;
    stejny udaj ukazuje admin Karty. Daniel 2026-10-15."""
    return any(cu.najem_lze_zdanit(card.client)
               for cu in card.card_units.select_related("unit__site__landlord"))


def _hlavicka_karty(card):
    """Hlavicka Karty: zvyrazneny nazev, volny radek, pak udaje.

    Daniel 2026-09-29: klient v hlavicce uz neni (je v nazvu Karty
    i v podpisech), Platnost od/do na jeden radek, oba pocty osob na
    jeden radek a hodnoty za dvojteckou odrazene tabem.

    Tabulator v PDF neexistuje - Paragraph ho vykresli jako mezeru. Proto
    je to tabulka o ctyrech sloupcich (popisek, hodnota, popisek,
    hodnota) a sirka kazdeho sloupce konci na zarazce tabulatoru; hodnoty
    pod sebou tak lici stejne jako ve Wordu."""
    nazev = card.description or f"Karta {card.client}"
    prvky = [
        Paragraph(escape(nazev), _STYLE_NAZEV_KARTY),
        Spacer(1, _STYLE_INFO.leading),  # 1 volny radek
    ]

    radky = []
    platnost = ["Platnost od:", format_date_cz(card.valid_from)]
    if card.valid_to:
        platnost += ["Platnost do:", format_date_cz(card.valid_to)]
    radky.append(platnost)
    # Pocty osob - klice na vodu, TUV a dalsi z nich berou vahu, takze musi
    # byt na Karte videt (Daniel 2026-09-25). Jsou to dve samostatna pole.
    osoby = []
    if card.pocet_osob is not None:
        osoby += ["Počet osob:", str(card.pocet_osob)]
    if card.pocet_osob_tuv is not None:
        osoby += ["Počet osob pro TUV:", str(card.pocet_osob_tuv)]
    if osoby:
        radky.append(osoby)
    # Platcovstvi rozhoduje, jestli se najem dani (viz poznamka pod
    # Pronajatymi plochami) - Daniel 2026-09-29.
    radky.append(["Plátce DPH:", "ano" if card.client.vat_payer else "ne",
                  "Nájemné s DPH:", "ano" if najem_s_dph(card) else "ne"])
    radky = [r + [""] * (4 - len(r)) for r in radky]

    font, velikost = _STYLE_INFO.fontName, _STYLE_INFO.fontSize
    sirky = [
        _na_tab(max(stringWidth(r[i], font, velikost) for r in radky))
        for i in range(4)
    ]
    tabulka = Table(radky, colWidths=sirky, hAlign="LEFT")
    tabulka.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), velikost),
        ("LEADING", (0, 0), (-1, -1), _STYLE_INFO.leading),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    prvky.append(tabulka)
    return prvky


def generate_client_card_document(card, output_path):
    """Vygeneruje Kartu nájemce (Příloha č. 1) pro danou ClientCard jako PDF
    a uloží do output_path (cesta nebo zapisovatelný stream, např. BytesIO)."""
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )
    elements = [Paragraph("Příloha č. 1 ke Smlouvě o nájmu", _STYLE_HEADER), Spacer(1, 4 * mm)]

    elements.extend(_hlavicka_karty(card))

    # --- Plochy ---
    elements.append(Paragraph("Pronajaté plochy", _STYLE_SEKCE))
    # Sloupec Vytapeno Daniel 2026-10-15 zrusil - v Karte nema co delat,
    # vytapena plocha je udaj pro rozuctovani tepla, ne pro najem.
    rows = [["Plocha", "Účel", "Výměra", "Cena (Kč/m²/rok)", "Nájemné/rok", "Nájemné/měsíc"]]

    total_area = Decimal("0")
    total_year = Decimal("0")
    total_month = Decimal("0")
    # Stejne poradi jako sekce Plochy a najemne v adminu (core.admin
    # CardUnitInline.get_queryset) - at vytistena Karta sedi s formularem.
    for cu in card.card_units.select_related("unit__site").order_by("unit__name"):
        area = cu.area_m2
        # cu.monthly_rent uz sjednanou pevnou castku resi (prebiji sazbu),
        # takze se z nej odvozuje i rocni najem - jinak by karta u takove
        # plochy tiskla prazdno. Viz Daniel 2026-08-17.
        month_rent = cu.monthly_rent
        year_rent = (month_rent * 12) if month_rent is not None else None

        # Ucel plochy (Unit.purpose) - Daniel 2026-10-15.
        radek = [str(cu.unit) if cu.unit else "—",
                 (cu.unit.purpose if cu.unit and cu.unit.purpose else "—"), _fmt_m2(area)]
        radek += [
            _fmt_kc(cu.rate_per_m2),
            _fmt_kc(year_rent, whole=True),
            _fmt_kc(month_rent, whole=True),
        ]
        rows.append(radek)

        total_area += area or Decimal("0")
        total_year += year_rent or Decimal("0")
        total_month += month_rent or Decimal("0")

    celkem = ["Celkem", "", _fmt_m2(total_area), "",
              _fmt_kc(total_year, whole=True), _fmt_kc(total_month, whole=True)]
    rows.append(celkem)

    units_table = Table(rows, repeatRows=1, hAlign="LEFT")
    units_table.setStyle(TableStyle([
        *_TABLE_BASE_STYLE,
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTNAME", (0, -1), (-1, -1), FONT_BOLD),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
    ]))
    elements.append(units_table)
    # Najem je podle §56a osvobozeny a dani se jen, kdyz jsou platci obe
    # strany a nejde o byt (CardUnit.najem_lze_zdanit). Jen tehdy ma
    # poznamka smysl - u neplatce by "bez DPH" budilo dojem, ze se DPH
    # jeste pripocte, a to nejde. Staci jedna zdanitelna plocha: karta
    # s bytem i kancelari (vzacne) ma cenu kancelare taky bez DPH.
    # Text upravil Daniel 2026-10-15 (drive "Cena najmu je uvedena bez DPH.").
    if najem_s_dph(card):
        elements.append(Paragraph(
            "K výše uvedeným částkám nájemného bude připočtena DPH.", _STYLE_POZNAMKA))

    # --- Poskytované služby (Daniel 2026-10-15) ---
    # a) Účtované služby vždy za měsíc - pevné částky a paušály (Pevná
    #    částka, Dle výměry), klient je platí každý měsíc bez ohledu na
    #    spotřebu;
    # b) Evidence pro výpočet - všechny ostatní klíče (podíly podle váhy
    #    a měřidel), podle kterých se rozúčtovává skutečný náklad.
    # Dřív to byla jedna tabulka "Klíče rozúčtování služeb".
    elements.append(Paragraph("Poskytované služby", _STYLE_SEKCE))
    # Stejne razeni jako sekce Klicu v adminu (core.admin
    # AllocationKeyInlineBase.get_queryset): v ramci Polozky zasobniku
    # jeste podle Podruzneho meridla, klic bez meridla prvni - at Karta
    # v PDF sedi s tim, co je videt ve formulari. Daniel 2026-08-26.
    #
    # nulls_first se pise vyslovne: Postgres radi prazdne hodnoty pri
    # vzestupnem razeni na KONEC, sqlite na zacatek.
    keys = list(
        card.allocation_keys
        .select_related("service_item", "meter", "client_card")
        .order_by(
            "service_item__invoice_class", "service_item__name",
            F("meter__code").asc(nulls_first=True), "pk",
        )
    )
    t = AllocationKey.AllocationType
    # Do a) jen pevne castky, ktere se opravdu fakturuji - sloupec
    # Fakturovat Daniel 2026-10-15 zrusil, takze nefakturovana pevna castka
    # (napr. srazkove vody "v pausalu") by tu vypadala jako uctovana.
    # Patri do b) mezi podklady pro vypocet.
    pausalni = [k for k in keys
                if k.allocation_type in (t.FIXED_AMOUNT, t.AREA_PRICE) and k.is_billed]
    evidence = [k for k in keys if k not in pausalni]

    # Poradi i nazvy Trid se berou z DB (Nastaveni -> Tridy) az za behu -
    # na urovni modulu by to byl dotaz uz pri importu (pada pri migrate).
    class_labels = InvoiceClassColor.label_map()
    class_order = [code for code, _ in InvoiceClassColor.choices()]

    # a) Účtované služby vždy za měsíc
    elements.append(Paragraph("a) Účtované služby vždy za měsíc", _STYLE_H3))
    if pausalni:
        obdobi = Period.current()
        pausal_rows = [["Položka", "Výpočet", "Kč/měsíc"]]
        celkem_mesic = Decimal("0")
        for class_code in class_order:
            for key in [k for k in pausalni if k.service_item.invoice_class == class_code]:
                vypocet, mesicne = _pausal_za_mesic(key, obdobi)
                pausal_rows.append([key.service_item.name, vypocet, _fmt_kc(mesicne)])
                if mesicne is not None:
                    celkem_mesic += mesicne
        pausal_rows.append(["Celkem za měsíc", "", _fmt_kc(celkem_mesic)])
        pausal_table = Table(pausal_rows, repeatRows=1, hAlign="LEFT")
        pausal_table.setStyle(TableStyle([
            *_TABLE_BASE_STYLE,
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("FONTNAME", (0, -1), (-1, -1), FONT_BOLD),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ]))
        elements.append(pausal_table)
    else:
        elements.append(Paragraph("Karta nemá žádné pevné částky ani paušály.", _STYLE_POZNAMKA))

    # b) Evidence pro výpočet
    # Od tohoto mista az po podpisy drzet pohromade (KeepTogether nize):
    # jinak se stavalo, ze na posledni strane zbyly jen podpisy (MI Roads).
    # Kdyz se blok na stranu nevejde, presune se cely na dalsi; delsi nez
    # strana se rozdeli normalne. Daniel 2026-10-15.
    zaver_od = len(elements)
    elements.append(Paragraph("b) Evidence pro výpočet", _STYLE_H3))
    # Ktera meridla karta s nekym sdili - rozhoduje o tom, jestli se
    # u klice tiskne vaha, nebo pomlcka (viz _fmt_key_value).
    sdilena = _sdilena_meridla(evidence)

    key_rows = [["Položka", "Měřidlo", "Typ výpočtu", "Hodnota"]]
    type_labels = dict(AllocationKey.AllocationType.choices)
    class_header_rows = []  # indexy radku s nazvem tridy - pro silnejsi linku/tucne pismo

    for class_code in class_order:
        class_keys = [k for k in evidence if k.service_item.invoice_class == class_code]
        if not class_keys:
            continue
        class_header_rows.append(len(key_rows))
        key_rows.append([class_labels[class_code], "", "", ""])
        for key in class_keys:
            key_rows.append([
                key.service_item.name,
                str(key.meter) if key.meter else "—",
                type_labels.get(key.allocation_type, key.allocation_type),
                _fmt_key_value(
                    key, (key.service_item_id, key.meter_id) in sdilena
                ),
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
    else:
        elements.append(Paragraph("Karta nemá žádné další klíče rozúčtování.", _STYLE_POZNAMKA))
    # Plati pro kazdou Kartu bez ohledu na platcovstvi - Daniel 2026-09-29:
    # "Karty najemcu musi obsahovat poznamku, ze vsechny ceny sluzeb jsou
    # uvedeny bez DPH."
    elements.append(Paragraph("Všechny ceny služeb jsou uvedeny bez DPH.", _STYLE_POZNAMKA))

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
    elements[zaver_od:] = [KeepTogether(elements[zaver_od:])]

    # --- Plánky pater, kde má karta plochy (každý na vlastní straně) ---
    elements.extend(_planek_stranky(card, doc.width, doc.height - 20 * mm))

    doc.build(elements, canvasmaker=_NumberedCanvas)
    return output_path
