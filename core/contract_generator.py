"""
Generovani dokumentu Smlouvy (.docx) z sablony core/contract_templates/smlouva_fm_template.docx.

Sablona NENI cisty formular - je to kopie realne drivejsi smlouvy (CALAMARI SE / CSE),
u ktere je jen blok najemce v zahlavi resetovany na placeholdery "[•]". Ostatni promenne udaje
(datumy, castky, vypovedni lhuta, podpisovy radek) jsou v sablone napevno dosazene z
puvodni smlouvy a nahrazuji se zde primo podle indexu odstavce - viz PLACEHOLDER_INDEXES.

Pozor: pokud se sablona (core/contract_templates/smlouva_fm_template.docx) v budoucnu
prepise jinou verzi, indexy odstavcu se mohou posunout a je potreba je znovu overit
(napr. skriptem, ktery vypise cislovane odstavce a najde ocekavany text).
"""
from decimal import Decimal
from pathlib import Path

import docx
from docx.opc.constants import RELATIONSHIP_TYPE as _RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

TEMPLATE_PATH = Path(__file__).resolve().parent / "contract_templates" / "smlouva_fm_template.docx"

# Pronajimatel (CALAMARI SE) je v teto sablone vzdy stejny - zastupuje ho Ing. Daniel David,
# jak uz je uvedeno v pevne casti zahlavi smlouvy (odstavec 13).
LANDLORD_NAME = "CALAMARI SE"
LANDLORD_REPRESENTATIVE = "Ing. Daniel DAVID"

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


def format_months(n):
    if n is None:
        return ""
    if n == 1:
        return f"{n} měsíc"
    if 2 <= n <= 4:
        return f"{n} měsíce"
    return f"{n} měsíců"


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


def _replace_substring(paragraph, old, new):
    _set_paragraph_text(paragraph, paragraph.text.replace(old, new))


def _clear_paragraph(paragraph):
    for run in list(paragraph.runs):
        run._element.getparent().remove(run._element)


def _add_hyperlink(paragraph, url, text):
    """Prida klikatelny odkaz (napr. mailto:) na konec odstavce jako novy run."""
    part = paragraph.part
    r_id = part.relate_to(url, _RT.HYPERLINK, is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    rpr.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rpr.append(underline)
    run.append(rpr)

    t = OxmlElement("w:t")
    t.text = text
    run.append(t)

    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def fill_contract_template(data, output_path, template_path=TEMPLATE_PATH):
    """
    `data` je dict s klici:
      site_name, client_name, client_address (jednoradkovy retezec),
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

    header_para = doc.sections[0].header.paragraphs[0]
    _set_paragraph_text(header_para, f"{data.get('site_name') or ''}\t\t{LANDLORD_NAME} / {client_name}")

    # --- blok Najemce v zahlavi (odstavce 19-25) ---
    _set_paragraph_text(p[19], client_name)
    _set_paragraph_text(p[20], f"se sídlem {data.get('client_address') or ''}")
    _set_paragraph_text(p[21], f"IČ: {data.get('client_ico') or ''}")

    dic = (data.get("client_dic") or "").strip()
    dic_digits = dic[2:] if dic.upper().startswith("CZ") else dic
    _set_paragraph_text(p[22], f"DIČ: CZ{dic_digits}")

    court = _court_instrumental(data.get("registry_court"))
    section = data.get("registry_section") or ""
    insert = data.get("registry_insert") or ""
    _set_paragraph_text(
        p[23],
        f"společnost zapsaná v obchodním rejstříku vedeném {court}, oddíl {section}, vložka {insert}",
    )

    _set_paragraph_text(
        p[24],
        f"zastoupena {data.get('representative_name') or ''}, {data.get('representative_role') or ''}",
    )
    email = data.get("invoicing_email") or ""
    _clear_paragraph(p[25])
    p[25].add_run("e-mailová adresa pro elektronickou fakturaci: ")
    if email:
        _add_hyperlink(p[25], f"mailto:{email}", email)

    # --- promenne udaje v telu smlouvy (indexy overeny proti aktualni sablone) ---
    _replace_substring(p[61], "[datum podpisu]", format_date_cz(data.get("signed_on")))
    _replace_substring(p[74], "1. ledna 2025", format_date_cz(data.get("inflation_increase_from")))
    _replace_substring(p[106], "XXXX Kč", format_czk(data.get("insurance_amount_czk")))
    _replace_substring(p[132], "1. prosince 2019", format_date_cz(data.get("valid_from")))
    _replace_substring(p[135], "6 měsíců", format_months(data.get("notice_period_months")))
    _replace_substring(p[159], "XX.XXX Kč", format_czk(data.get("deposit_czk")))
    _replace_substring(p[201], "3. února 2024", format_date_cz(data.get("signed_on")))

    # --- podpisovy radek (odstavce 208-209 jsou pozustatek puvodni smlouvy) ---
    tenant_rep = data.get("representative_name") or ""
    _set_paragraph_text(p[208], f"\tza Pronajímatele: {LANDLORD_REPRESENTATIVE}\tza Nájemce: {tenant_rep}")
    _set_paragraph_text(p[209], "")

    # python-docx prijima jak cestu (str/Path), tak zapisovatelny stream (napr. BytesIO)
    doc.save(output_path if hasattr(output_path, "write") else str(output_path))
    return output_path
