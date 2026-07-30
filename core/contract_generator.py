"""
Generovani dokumentu Smlouvy (.docx) z sablony core/contract_templates/smlouva_fm_template.docx.

Sablona NENI cisty formular - je to kopie realne drivejsi smlouvy (CALAMARI SE / CSE),
u ktere je blok najemce v zahlavi resetovany na placeholdery "[•]" a promenne udaje
(datumy, castky, vypovedni lhuta) na bracketove/textove placeholdery jako "[datum podpisu]"
nebo "XXXX Kč" - ty se dohledavaji podle textu (viz _find_paragraph), ne podle indexu, takze
jsou odolne vuci zmene poctu odstavcu jinde v dokumentu.

Clanek 1 (Vymezeni predmetu a ucelu najmu) je pro kazdy areal jiny (vypis jinych pozemku/budov) -
jeho text se necte ze sablony, ale z core.models.Site.lease_subject_text (viz _fill_article1).
Pocet odstavcu vycetu nemovitosti se tak muze mezi generovanimi lisit → cokoli za clankem 1 se
MUSI dohledavat podle textu, ne podle pevneho indexu (na rozdil od bloku najemce v zahlavi,
ktery je pred clankem 1 a indexy tam zustavaji stabilni).
"""
import copy
from decimal import Decimal
from pathlib import Path

import docx
from docx.enum.text import WD_COLOR_INDEX
from docx.opc.constants import RELATIONSHIP_TYPE as _RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph

TEMPLATE_PATH = Path(__file__).resolve().parent / "contract_templates" / "smlouva_fm_template.docx"

# Bezna velikost textu ve Smlouve (viz napr. clanek 1) - u noveho runu vytvoreneho
# pres paragraph.add_run() se NEDEDI formatovani od sousednich runu ani od pPr
# odstavce, jinak spadne na vychozi styl dokumentu (11pt) - proto se vynucuje
# explicitne u kazdeho nove vytvoreneho runu (viz _set_paragraph_runs/_set_paragraph_text).
BODY_FONT_SIZE = Pt(8)
BODY_FONT_NAME = "Arial Narrow"

_MONTHS = [
    "ledna", "února", "března", "dubna", "května", "června",
    "července", "srpna", "září", "října", "listopadu", "prosince",
]

# Male, uzavrene mnozina soudu vedoucich obchodni rejstrik v CR - staci pro spravny
# gramaticky pad (7. pad/instrumental) v pripadech, ktere se v praxi objevi.
_COURT_INSTRUMENTAL_PREFIXES = {
    "krajský soud v": "krajským soudem v",
    "městský soud v praze": "městským soudem v Praze",
}


def _court_instrumental(court_name):
    """'Krajský soud v Ostravě' -> 'Krajským soudem v Ostravě'. Neznamy tvar se
    vrati beze zmeny - v generovanem dokumentu je pak potreba rucne zkontrolovat pad."""
    if not court_name:
        return ""
    lowered = court_name.strip().lower()
    for prefix, replacement in _COURT_INSTRUMENTAL_PREFIXES.items():
        if lowered.startswith(prefix):
            rest = court_name.strip()[len(prefix):]
            # replacement uz ma spravnou velikost pismen na zacatku (mimo Praha)
            first_word, _, tail = replacement.partition(" ")
            return f"{first_word[0].upper()}{first_word[1:]} {tail}{rest}".rstrip()
    return court_name.strip()


def format_date_cz(d):
    if not d:
        return ""
    return f"{d.day}. {_MONTHS[d.month - 1]} {d.year}"


def format_czk(amount):
    if amount is None:
        return ""
    if isinstance(amount, Decimal):
        amount = int(amount)
    return f"{amount:,}".replace(",", " ") + " Kč"


def get_landlord():
    """Vrati Klienta oznaceneho jako Pronajimatel (Client.is_landlord=True).

    Aplikace pocita s tim, ze takovy Klient je v databazi prave jeden -
    vynucuje se to na urovni admin formulare (Client.clean(), viz core/models.py),
    ne na urovni databaze, takze tato funkce prípadnou duplicitu neresí a
    jednoduse vezme prvniho nalezeneho."""
    from core.models import Client
    landlord = Client.objects.filter(is_landlord=True).first()
    if landlord is None:
        raise ValueError(
            "V databazi neni zadny Klient oznaceny jako Pronajimatel - "
            "oznac prislusneho Klienta prepinacem 'Pronajímatel' v adminu."
        )
    return landlord


def _format_address(obj):
    address = " ".join(p for p in (obj.street, obj.street_number) if p)
    if obj.zip_code or obj.city:
        address = f"{address}, {obj.zip_code} {obj.city}".strip(", ")
    return address


def contract_to_template_data(contract):
    """Sestavi `data` dict pro fill_contract_template() z instance Contract
    (a jejiho navazaneho Client) - sdileno mezi hromadnou akci v seznamu
    Smluv a tlacitkem generovani na detailu jedne Smlouvy."""
    client = contract.client
    landlord = get_landlord()

    return {
        "site_name": str(contract.site) if contract.site else "",
        "lease_subject_text": (contract.site.lease_subject_text if contract.site else "") or "",
        "landlord_name": landlord.name,
        "landlord_address": _format_address(landlord),
        "landlord_ico": landlord.ico,
        "landlord_dic": landlord.dic,
        "landlord_bank_name": landlord.bank_name,
        "landlord_bank_account": landlord.bank_account,
        "landlord_bank_code": landlord.bank_code,
        "landlord_registry_court": landlord.registry_court,
        "landlord_registry_section": landlord.registry_section,
        "landlord_registry_insert": landlord.registry_insert,
        "landlord_representative_name": landlord.representative_name,
        "landlord_representative_role": landlord.representative_role,
        "client_name": client.name,
        "client_address": _format_address(client),
        "client_ico": client.ico,
        "client_dic": client.dic,
        "registry_court": client.registry_court,
        "registry_section": client.registry_section,
        "registry_insert": client.registry_insert,
        "representative_name": contract.representative_name,
        "representative_role": contract.representative_role,
        "invoicing_email": contract.invoicing_email,
        "signed_on": contract.signed_on,
        "valid_from": contract.valid_from,
        "notice_period_months": contract.notice_period_months,
        "insurance_amount_czk": contract.insurance_amount_czk,
        "deposit_czk": contract.deposit_czk,
        "inflation_increase_from": contract.inflation_increase_from,
    }


def format_months(n):
    if n is None:
        return ""
    if n == 1:
        return f"{n} měsíc"
    if 2 <= n <= 4:
        return f"{n} měsíce"
    return f"{n} měsíců"


def _force_font(paragraph):
    """Vynuti BODY_FONT_SIZE/BODY_FONT_NAME na vsech runech odstavce - viz
    poznamka u BODY_FONT_SIZE, proc je to potreba."""
    for run in paragraph.runs:
        run.font.size = BODY_FONT_SIZE
        run.font.name = BODY_FONT_NAME


def _set_paragraph_text(paragraph, text):
    """Prepise cely text odstavce do jednoho runu (zachova font/styl prvniho
    puvodniho runu, pokud existoval). Nehodi se pro odstavce s vice styly textu
    v jedne vete (tady zadny takovy mezi upravovanymi odstavci neni)."""
    runs = list(paragraph.runs)
    if runs:
        runs[0].text = text
        for run in runs[1:]:
            run._element.getparent().remove(run._element)
    else:
        paragraph.add_run(text)
    _force_font(paragraph)


def _clear_paragraph(paragraph):
    for run in list(paragraph.runs):
        run._element.getparent().remove(run._element)


def _set_paragraph_runs(paragraph, parts):
    """Prepise odstavec podle `parts` = seznam dvojic (text, zvyraznit).
    Kazda dvojice se stane samostatnym runem; zvyraznit=True dostane sedy
    zvyraznovac (font.highlight_color) - na rozdil od zlute zustane citelny
    i po cernobilem tisku - aby bylo v dokumentu na prvni pohled videt,
    ktere hodnoty se doplnily z dat Smlouvy/Klienta."""
    _clear_paragraph(paragraph)
    for text, highlight in parts:
        if not text:
            continue
        run = paragraph.add_run(text)
        run.font.size = BODY_FONT_SIZE
        run.font.name = BODY_FONT_NAME
        if highlight:
            run.font.highlight_color = WD_COLOR_INDEX.GRAY_25


def _replace_substring_highlighted(paragraph, old, new):
    """Nahradi vyskyt `old` v odstavci za `new` a zvyrazni jen `new` cast -
    okolni puvodni text vety zustane beze zmeny stylu."""
    text = paragraph.text
    idx = text.find(old)
    if idx == -1:
        return
    before, after = text[:idx], text[idx + len(old):]
    _set_paragraph_runs(paragraph, [(before, False), (new, True), (after, False)])


def _add_hyperlink(paragraph, url, text, highlight=False):
    """Prida klikatelny odkaz (napr. mailto:) na konec odstavce jako novy run."""
    part = paragraph.part
    r_id = part.relate_to(url, _RT.HYPERLINK, is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    rfonts = OxmlElement("w:rFonts")
    rfonts.set(qn("w:ascii"), BODY_FONT_NAME)
    rfonts.set(qn("w:hAnsi"), BODY_FONT_NAME)
    rpr.append(rfonts)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(BODY_FONT_SIZE.pt * 2)))
    rpr.append(sz)
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    rpr.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rpr.append(underline)
    if highlight:
        hl = OxmlElement("w:highlight")
        hl.set(qn("w:val"), "lightGray")
        rpr.append(hl)
    run.append(rpr)

    t = OxmlElement("w:t")
    t.text = text
    run.append(t)

    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def _find_paragraph_index(paragraphs, marker):
    """Vrati index prvniho odstavce obsahujiciho `marker`, nebo vyhodi
    ValueError - pouziva se pro vse ZA clankem 1, protoze pocet jeho
    odstavcu je promenlivy (viz _fill_article1) a pevne indexy uz tam
    nejsou spolehlive."""
    for i, para in enumerate(paragraphs):
        if marker in para.text:
            return i
    raise ValueError(
        f"V šabloně smlouvy nenalezen odstavec obsahující {marker!r} - "
        f"zkontroluj core/contract_templates/smlouva_fm_template.docx."
    )


def _fill_article1(doc, lease_subject_text):
    """Dosadi text clanku 1 (Vymezeni predmetu a ucelu najmu) podle arealu.

    `lease_subject_text` je vicerádkový text (Site.lease_subject_text):
    prvni radek je uvodni veta (katastralni urad/LV/obec/k.u.), kazdy
    dalsi radek jeden pozemek/budova z vyctu. Uvodni odstavec sablony se
    prepise na miste; vycet pozemku/budov (puvodne pevny pocet odstavcu)
    se podle poctu radku bud zkrati (prebytecne odstavce smazou), nebo
    prodlouzi (posledni odrazkovy odstavec se naklonuje - sdili Word
    cislovani seznamu numId, viz modulovy docstring, takze klon zustane
    spravne formatovany i cislovany).

    Vraci pocet odstavcu, o ktery se cely dokument zmensil/zvetsil oproti
    puvodnimu stavu (kladne cislo = pribylo odstavcu) - volajici podle
    toho vi, ze indexy odstavcu ZA timto blokem uz nejsou spolehlive a
    musi je dohledavat podle textu.
    """
    paragraphs = doc.paragraphs
    # Presna shoda, ne substring - "Vymezení předmětu a účelu nájmu" se jako
    # PREFIX objevuje uz drive v Obsahu (napr. "Vymezení předmětu a účelu
    # nájmu\t3"), substring hledani (_find_paragraph_index) by tedy chybne
    # naslo radek Obsahu misto skutecneho nadpisu clanku.
    heading_idx = next(
        i for i, para in enumerate(paragraphs)
        if para.text.strip() == "Vymezení předmětu a účelu nájmu"
    )

    intro_idx = heading_idx + 1
    while not paragraphs[intro_idx].text.strip():
        intro_idx += 1

    stop_idx = intro_idx + 1
    while "Pronajímatel přenechává touto smlouvou" not in paragraphs[stop_idx].text:
        stop_idx += 1

    intro_para = paragraphs[intro_idx]
    bullet_paras = paragraphs[intro_idx + 1:stop_idx]

    lines = [line.strip() for line in (lease_subject_text or "").splitlines() if line.strip()]
    if not lines:
        _set_paragraph_runs(intro_para, [
            ("[DOPLNIT VYMEZENÍ PŘEDMĚTU NÁJMU PRO TENTO AREÁL - viz Areál v adminu]", True),
        ])
        for bp in bullet_paras:
            bp._p.getparent().remove(bp._p)
        return -len(bullet_paras)

    intro_text, bullet_lines = lines[0], lines[1:]
    _set_paragraph_runs(intro_para, [(intro_text, False)])

    n_existing = len(bullet_paras)
    n_needed = len(bullet_lines)

    for i in range(min(n_existing, n_needed)):
        _set_paragraph_runs(bullet_paras[i], [(bullet_lines[i], False)])

    if n_needed > n_existing:
        template_xml = bullet_paras[-1]._p if bullet_paras else intro_para._p
        anchor = template_xml
        for i in range(n_existing, n_needed):
            new_xml = copy.deepcopy(template_xml)
            anchor.addnext(new_xml)
            anchor = new_xml
            new_para = Paragraph(new_xml, bullet_paras[-1]._parent if bullet_paras else intro_para._parent)
            _set_paragraph_runs(new_para, [(bullet_lines[i], False)])
    elif n_needed < n_existing:
        for bp in bullet_paras[n_needed:]:
            bp._p.getparent().remove(bp._p)

    return n_needed - n_existing


def fill_contract_template(data, output_path, template_path=TEMPLATE_PATH):
    """
    `data` je dict s klici:
      site_name, lease_subject_text (viz core.models.Site.lease_subject_text),
      client_name, client_address (jednoradkovy retezec),
      client_ico, client_dic (s nebo bez "CZ" prefixu), registry_court,
      registry_section, registry_insert, representative_name, representative_role,
      invoicing_email, signed_on (date), valid_from (date),
      notice_period_months (int), insurance_amount_czk (Decimal/int),
      deposit_czk (Decimal/int), inflation_increase_from (date).

    Chybejici/None hodnoty se dosadi jako prazdny retezec - vysledny dokument
    je pak potreba pred odeslanim zkontrolovat.
    """
    doc = docx.Document(str(template_path))
    p = doc.paragraphs

    client_name = data.get("client_name") or ""
    landlord_name = data.get("landlord_name") or ""

    # Zahlavi dokumentu (nahoře na kazde strance) se NEZVYRAZNUJE - jen
    # identifikuje areal/smluvni strany, neni to "doplneny udaj" smlouvy.
    header_para = doc.sections[0].header.paragraphs[0]
    _set_paragraph_text(header_para, f"{data.get('site_name') or ''}\t\t{landlord_name} / {client_name}")

    # --- blok Pronajimatele v zahlavi (odstavce 6-13) - bere se z Klienta
    # oznaceneho Client.is_landlord=True (viz get_landlord()), NE ze
    # sablony - aplikace tak neni navazana na jednu konkretni firmu.
    # Neni to "doplneny udaj" teto konkretni Smlouvy (je stejny pro vsechny
    # Smlouvy), proto se stejne jako zahlavi NEZVYRAZNUJE. ---
    _set_paragraph_runs(p[6], [(landlord_name, False)])
    _set_paragraph_runs(p[7], [("se sídlem na adrese ", False), (data.get("landlord_address") or "", False)])
    _set_paragraph_runs(p[8], [("IČ: ", False), (data.get("landlord_ico") or "", False)])

    landlord_dic = (data.get("landlord_dic") or "").strip()
    landlord_dic_digits = landlord_dic[2:] if landlord_dic.upper().startswith("CZ") else landlord_dic
    _set_paragraph_runs(p[9], [("DIČ: CZ", False), (landlord_dic_digits, False)])

    _set_paragraph_runs(p[10], [("Bankovní spojení: ", False), (data.get("landlord_bank_name") or "", False)])
    bank_account = data.get("landlord_bank_account") or ""
    bank_code = data.get("landlord_bank_code") or ""
    account_display = f"{bank_account}/{bank_code}" if bank_code else bank_account
    _set_paragraph_runs(p[11], [("číslo účtu: ", False), (account_display, False)])

    landlord_court = _court_instrumental(data.get("landlord_registry_court"))
    _set_paragraph_runs(p[12], [
        ("Společnost zapsána v obchodním rejstříku vedeném ", False), (landlord_court, False),
        (", oddíl ", False), (data.get("landlord_registry_section") or "", False),
        (", vložka ", False), (data.get("landlord_registry_insert") or "", False),
    ])
    _set_paragraph_runs(p[13], [
        ("Společnost zastupuje: ", False), (data.get("landlord_representative_name") or "", False),
        (", ", False), (data.get("landlord_representative_role") or "", False),
    ])

    # --- blok Najemce v zahlavi (odstavce 19-25) - PRED clankem 1, indexy
    # tedy zustavaji stabilni bez ohledu na delku vyctu nemovitosti. ---
    _set_paragraph_runs(p[19], [(client_name, True)])
    _set_paragraph_runs(p[20], [("se sídlem ", False), (data.get("client_address") or "", True)])
    _set_paragraph_runs(p[21], [("IČ: ", False), (data.get("client_ico") or "", True)])

    dic = (data.get("client_dic") or "").strip()
    dic_digits = dic[2:] if dic.upper().startswith("CZ") else dic
    _set_paragraph_runs(p[22], [("DIČ: CZ", False), (dic_digits, True)])

    court = _court_instrumental(data.get("registry_court"))
    section = data.get("registry_section") or ""
    insert = data.get("registry_insert") or ""
    _set_paragraph_runs(p[23], [
        ("společnost zapsaná v obchodním rejstříku vedeném ", False), (court, True),
        (", oddíl ", False), (section, True),
        (", vložka ", False), (insert, True),
    ])

    _set_paragraph_runs(p[24], [
        ("zastoupena ", False), (data.get("representative_name") or "", True),
        (", ", False), (data.get("representative_role") or "", True),
    ])

    email = data.get("invoicing_email") or ""
    _clear_paragraph(p[25])
    run = p[25].add_run("e-mailová adresa pro elektronickou fakturaci: ")
    run.font.size = BODY_FONT_SIZE
    run.font.name = BODY_FONT_NAME
    if email:
        _add_hyperlink(p[25], f"mailto:{email}", email, highlight=True)

    # --- clanek 1: vlastni text podle arealu (meni pocet odstavcu dokumentu) ---
    _fill_article1(doc, data.get("lease_subject_text"))

    # --- vse ZA clankem 1: dohledavat podle textu, ne podle indexu (viz docstring) ---
    paragraphs = doc.paragraphs
    _replace_substring_highlighted(
        paragraphs[_find_paragraph_index(paragraphs, "[datum podpisu]")],
        "[datum podpisu]", format_date_cz(data.get("signed_on")),
    )
    paragraphs = doc.paragraphs
    _replace_substring_highlighted(
        paragraphs[_find_paragraph_index(paragraphs, "1. ledna 2025")],
        "1. ledna 2025", format_date_cz(data.get("inflation_increase_from")),
    )
    paragraphs = doc.paragraphs
    _replace_substring_highlighted(
        paragraphs[_find_paragraph_index(paragraphs, "XXXX Kč")],
        "XXXX Kč", format_czk(data.get("insurance_amount_czk")),
    )
    paragraphs = doc.paragraphs
    _replace_substring_highlighted(
        paragraphs[_find_paragraph_index(paragraphs, "1. prosince 2019")],
        "1. prosince 2019", format_date_cz(data.get("valid_from")),
    )
    paragraphs = doc.paragraphs
    _replace_substring_highlighted(
        paragraphs[_find_paragraph_index(paragraphs, "6 měsíců")],
        "6 měsíců", format_months(data.get("notice_period_months")),
    )
    paragraphs = doc.paragraphs
    _replace_substring_highlighted(
        paragraphs[_find_paragraph_index(paragraphs, "XX.XXX Kč")],
        "XX.XXX Kč", format_czk(data.get("deposit_czk")),
    )
    paragraphs = doc.paragraphs
    _replace_substring_highlighted(
        paragraphs[_find_paragraph_index(paragraphs, "3. února 2024")],
        "3. února 2024", format_date_cz(data.get("signed_on")),
    )

    # --- podpisovy radek: nadpis "Pronajímatel/Nájemce" a cara pod nim jsou
    # staticky text sablony (stejne pro kazdou Smlouvu, viz odstavce pred
    # "CEA SSF" v sablone) - doplnuje se jen radek se jmeny zastupcu, na
    # miste puvodniho placeholderu "CEA SSF\tXXXX" (pozustatek puvodni
    # smlouvy, viz modulovy docstring). ---
    paragraphs = doc.paragraphs
    names_idx = _find_paragraph_index(paragraphs, "CEA SSF")
    landlord_rep = data.get("landlord_representative_name") or ""
    tenant_rep = data.get("representative_name") or ""

    _set_paragraph_runs(paragraphs[names_idx], [
        (landlord_rep, False), ("\t", False), (tenant_rep, True),
    ])

    # python-docx prijima jak cestu (str/Path), tak zapisovatelny stream (napr. BytesIO)
    doc.save(output_path if hasattr(output_path, "write") else str(output_path))
    return output_path
