"""
Generovani dokumentu Smlouvy (.docx) z sablony core/contract_templates/smlouva_template.docx.

Sablona NENI cisty formular s placeholdery - je to skutecna, rucne doladena
smlouva (konkretni najemce, konkretni castky, data, jmena). Generovani proto
funguje tak, ze najde konkretni run(y) obsahujici tyto puvodni hodnoty a
prepise jen jejich TEXT - format (font, velikost, barva, zvyrazneni...)
kazdeho runu se nikde nevynucuje ani nemeni, zustava presne takovy, jaky uz
v sablone je. Kde sablona nema zvyrazneni doplnenych udaju, nema ho ani
vygenerovany dokument.

Blok Pronajimatele v zahlavi dokumentu (odstavce 6-13) je zamerne staticky -
Pronajimatel (CALAMARI SE) je v teto aplikaci jeden jediny a v sablone uz ma
spravne udaje; dynamicky se doplnuje jen tam, kde je to bezriziko (nazev
v zahlavi kazde stranky, jmeno zastupce v podpisovem radku - viz nize).

Clanek 1 (Vymezeni predmetu a ucelu najmu) je pro kazdy areal jiny (vypis
jinych pozemku/budov) - jeho text se necte ze sablony, ale z
core.models.Site.lease_subject_text (viz _fill_article1). Pocet odstavcu
vycetu nemovitosti se tak muze mezi generovanimi lisit → cokoli za clankem 1
se MUSI dohledavat podle textu, ne podle pevneho indexu (na rozdil od bloku
najemce v zahlavi, ktery je pred clankem 1 a indexy tam zustavaji stabilni).
"""
import copy
from decimal import Decimal
from pathlib import Path

import docx
from docx.opc.constants import RELATIONSHIP_TYPE as _RT
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

TEMPLATE_PATH = Path(__file__).resolve().parent / "contract_templates" / "smlouva_template.docx"

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
        "landlord_representative_name": landlord.representative_name,
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


def _set_paragraph_text_keep_format(paragraph, text):
    """Prepise cely text odstavce do jednoho runu - PONECHA font/velikost/barvu
    puvodniho prvniho runu (pokud existoval), nic se nevynucuje. Nehodi se pro
    odstavce s vice styly textu v jedne vete (tady zadny takovy mezi
    upravovanymi odstavci neni)."""
    runs = list(paragraph.runs)
    if runs:
        runs[0].text = text
        for run in runs[1:]:
            run._element.getparent().remove(run._element)
    else:
        paragraph.add_run(text)


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
        f"zkontroluj core/contract_templates/smlouva_template.docx."
    )


def _replace_run_text(paragraphs, marker, old, new):
    """Najde odstavec obsahujici `marker` (unikatni text pro dohledani spravneho
    mista - napr. cely puvodni datum, ne jen cislo, aby se nespletlo s jinym
    vyskytem stejne hodnoty jinde ve smlouve) a v nem run obsahujici `old`;
    v tomto runu nahradi `old` za `new`. Format runu (font, velikost, barva)
    se nemeni, meni se jen text."""
    idx = _find_paragraph_index(paragraphs, marker)
    para = paragraphs[idx]
    for run in para.runs:
        if old in run.text:
            run.text = run.text.replace(old, new)
            return
    raise ValueError(
        f"Marker {old!r} nalezen v odstavci {idx}, ale ne v samostatnem runu - "
        f"zkontroluj core/contract_templates/smlouva_template.docx."
    )


def _set_hyperlink(paragraph, new_url, new_text):
    """Prepise text a cil existujiciho hypertextoveho odkazu (w:hyperlink)
    v odstavci - pouziva se pro e-mailovou adresu pro elektronickou fakturaci.
    Bez `new_url` (prazdny e-mail) se odkaz cely odstrani - jinak by v dokumentu
    zustal "mrtvy" odkaz na puvodni (uz nespravnou) adresu ze sablony. Jinak
    puvodni vztah (relationship) na starou URL se ponecha nevyuzity (neskodi),
    misto prepisu se jen prida novy a hyperlink se prepoji na nej."""
    hyperlink_el = paragraph._p.find(qn("w:hyperlink"))
    if hyperlink_el is None:
        return
    if not new_url:
        hyperlink_el.getparent().remove(hyperlink_el)
        return
    t_el = hyperlink_el.find(".//" + qn("w:t"))
    if t_el is not None:
        t_el.text = new_text
    new_r_id = paragraph.part.relate_to(new_url, _RT.HYPERLINK, is_external=True)
    hyperlink_el.set(qn("r:id"), new_r_id)


def _fill_article1(doc, lease_subject_text):
    """Dosadi text clanku 1 (Vymezeni predmetu a ucelu najmu) podle arealu.

    `lease_subject_text` je vicerádkový text (Site.lease_subject_text):
    prvni radek je uvodni veta (katastralni urad/LV/obec/k.u.), kazdy
    dalsi radek jeden pozemek/budova z vyctu. Uvodni odstavec sablony se
    prepise na miste; vycet pozemku/budov (puvodne pevny pocet odstavcu)
    se podle poctu radku bud zkrati (prebytecne odstavce smazou), nebo
    prodlouzi (posledni odrazkovy odstavec se naklonuje - sdili Word
    cislovani seznamu numId, takze klon zustane spravne formatovany
    i cislovany, vc. puvodniho fontu).

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
        _set_paragraph_text_keep_format(
            intro_para,
            "[DOPLNIT VYMEZENÍ PŘEDMĚTU NÁJMU PRO TENTO AREÁL - viz Areál v adminu]",
        )
        for bp in bullet_paras:
            bp._p.getparent().remove(bp._p)
        return -len(bullet_paras)

    intro_text, bullet_lines = lines[0], lines[1:]
    _set_paragraph_text_keep_format(intro_para, intro_text)

    n_existing = len(bullet_paras)
    n_needed = len(bullet_lines)

    for i in range(min(n_existing, n_needed)):
        _set_paragraph_text_keep_format(bullet_paras[i], bullet_lines[i])

    if n_needed > n_existing:
        template_xml = bullet_paras[-1]._p if bullet_paras else intro_para._p
        anchor = template_xml
        for i in range(n_existing, n_needed):
            new_xml = copy.deepcopy(template_xml)
            anchor.addnext(new_xml)
            anchor = new_xml
            new_para = Paragraph(new_xml, bullet_paras[-1]._parent if bullet_paras else intro_para._parent)
            _set_paragraph_text_keep_format(new_para, bullet_lines[i])
    elif n_needed < n_existing:
        for bp in bullet_paras[n_needed:]:
            bp._p.getparent().remove(bp._p)

    return n_needed - n_existing


def fill_contract_template(data, output_path, template_path=TEMPLATE_PATH):
    """
    `data` je dict s klici:
      site_name, lease_subject_text (viz core.models.Site.lease_subject_text),
      landlord_name, landlord_representative_name,
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

    client_name = data.get("client_name") or ""
    landlord_name = data.get("landlord_name") or ""

    # --- zahlavi dokumentu (nahoře na kazde strance): 3 runy - kod/nazev
    # arealu, tabulator, "Pronajimatel / Najemce" ---
    header_para = doc.sections[0].header.paragraphs[0]
    header_runs = header_para.runs
    header_runs[0].text = data.get("site_name") or ""
    header_runs[-1].text = "\t" + f"{landlord_name} / {client_name}"

    # --- blok Najemce v zahlavi (odstavce 19-25, PRED clankem 1 - indexy
    # tedy zustavaji stabilni bez ohledu na delku vyctu nemovitosti v cl. 1).
    # Blok Pronajimatele (6-13) je zamerne staticky, viz modulovy docstring. ---
    paragraphs = doc.paragraphs
    paragraphs[19].runs[0].text = client_name
    paragraphs[20].runs[-1].text = data.get("client_address") or ""
    paragraphs[21].runs[-1].text = data.get("client_ico") or ""

    dic = (data.get("client_dic") or "").strip()
    dic_digits = dic[2:] if dic.upper().startswith("CZ") else dic
    paragraphs[22].runs[0].text = "DIČ: CZ" + dic_digits

    court = _court_instrumental(data.get("registry_court"))
    section = data.get("registry_section") or ""
    insert = data.get("registry_insert") or ""
    reg_runs = paragraphs[23].runs
    reg_runs[1].text = court
    reg_runs[3].text = section
    reg_runs[5].text = insert

    rep_runs = paragraphs[24].runs
    rep_runs[1].text = data.get("representative_name") or ""
    rep_runs[3].text = data.get("representative_role") or ""

    email = data.get("invoicing_email") or ""
    _set_hyperlink(paragraphs[25], f"mailto:{email}" if email else None, email)

    # --- clanek 1: vlastni text podle arealu (meni pocet odstavcu dokumentu) ---
    _fill_article1(doc, data.get("lease_subject_text"))

    # --- vse ZA clankem 1: dohledavat podle textu, ne podle indexu (viz docstring) ---
    paragraphs = doc.paragraphs
    _replace_run_text(
        paragraphs, "1. ledna 2027", "1. ledna 2027",
        format_date_cz(data.get("inflation_increase_from")),
    )
    paragraphs = doc.paragraphs
    _replace_run_text(
        paragraphs, "50 000 Kč", "50 000 Kč",
        format_czk(data.get("insurance_amount_czk")),
    )
    paragraphs = doc.paragraphs
    _replace_run_text(
        paragraphs, "1. srpna 2026", "1. srpna 2026",
        format_date_cz(data.get("valid_from")),
    )
    paragraphs = doc.paragraphs
    _replace_run_text(
        paragraphs, "3 měsíce", "3 měsíce",
        format_months(data.get("notice_period_months")),
    )
    paragraphs = doc.paragraphs
    _replace_run_text(
        paragraphs, "15 000 Kč", "15 000 Kč",
        format_czk(data.get("deposit_czk")),
    )
    paragraphs = doc.paragraphs
    _replace_run_text(
        paragraphs, "V\xa0Ostravě dne 30. července 2026", "30. července 2026",
        format_date_cz(data.get("signed_on")),
    )

    # --- podpisovy radek: jmena zastupcu pod carou a pod nimi nazvy
    # smluvnich stran (nadpis "Pronajímatel/Nájemce" a cara nad nimi jsou
    # staticky text sablony, viz modulovy docstring) ---
    paragraphs = doc.paragraphs
    names_idx = _find_paragraph_index(paragraphs, "\tIng. Daniel DAVID")
    names_runs = paragraphs[names_idx].runs
    names_runs[0].text = "\t" + (data.get("landlord_representative_name") or "")
    names_runs[-1].text = data.get("representative_name") or ""

    _set_paragraph_text_keep_format(
        paragraphs[names_idx + 1],
        "\t" + landlord_name + "\t" + client_name,
    )

    # python-docx prijima jak cestu (str/Path), tak zapisovatelny stream (napr. BytesIO)
    doc.save(output_path if hasattr(output_path, "write") else str(output_path))
    return output_path
