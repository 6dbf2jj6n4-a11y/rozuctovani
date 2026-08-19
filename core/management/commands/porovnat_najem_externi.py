"""
Porovná roční nájem a plátcovství DPH z externího výpočtu (tabulka od
Daniela) proti naší DB. Páruje se podle IČO - názvy se v obou zdrojích
píší jinak ("Outdoor Colours" vs "Outdoor & Colours s.r.o.",
"MEON EMS FM" vs "MEON EMS Frýdek-Místek"), takže na název se spoléhat
nedá; slouží jen jako záložní klíč, když IČO nesedí.

Naše roční částka = součet ploch karty × sazba Kč/m²/rok přes VŠECHNY
aktivní karty klienta (klient jich může mít víc). Záměrně se porovnává
ROČNÍ částka - naše měsíční se zaokrouhluje nahoru na celé koruny
(tak se fakturuje), takže by měsíční srovnání hlásilo haléřové rozdíly
u každého řádku.

Použití:
  python manage.py porovnat_najem_externi
  python manage.py porovnat_najem_externi --tolerance 10
"""
import unicodedata
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.models import Client, ClientCard

# (nazev, ICO, platce DPH ano/ne, rocni najem)
EXTERNI = [
    ("Artalo design s. r. o.", "10888560", "ano", "1450000.00"),
    ("Candee Candles, s.r.o.", "10999507", "ano", "66150.00"),
    ("Dalibor HOLUB", "68324014", "ne", "43200.00"),
    ("Detektivo Games s.r.o.", "23674555", "ano", "289250.00"),
    ("Fitclub Cross Body MT s. r. o.", "05427754", "ano", "543660.00"),
    ("GENERAL ARMY spol. s r. o.", "47153750", "ano", "684240.00"),
    ("Ing. Roman CHAMRAD - SHIVA SHOP", "65475259", "ano", "452100.00"),
    ("Kateřina Špačková", "04514807", "ne", "43799.80"),
    ("Kyslík pro život, s. r. o.", "28589572", "ano", "89460.00"),
    ("Leoš DUDA", "44927665", "ano", "120150.00"),
    ("LogicVision s. r. o.", "01386662", "ano", "1377910.00"),
    ("MAR-COMPLEX s.r.o.", "26807998", "ano", "32300.00"),
    ("MEON EMS FM, s. r. o.", "09961836", "ne", "202130.00"),
    ("Mgr. Lucie Halamová", "29594782", "ne", "43200.00"),
    ("Milan BOLGÁČ", "66746400", "ano", "85050.00"),
    ("Milan ŠPRC", "12092371", "ano", "32400.00"),
    ("NORVITT ENGINEERING, spol. s r. o.", "29395381", "ano", "116930.00"),
    ("Outdoor Colours, s. r. o.", "28609042", "ano", "81000.00"),
    ("PELUS automation machines s.r.o.", "01422260", "ano", "457675.00"),
    ("PROJEKTY STATIKA s. r. o.", "28605543", "ne", "76075.50"),
    ("PTÁČEK-velkoobchod, a.s", "25501143", "ano", "3124563.00"),
    ("Robert KALETA", "68355050", "ne", "74800.00"),
    ("Taneční skupina Aktiv z.s.", "23429852", "ne", "519600.00"),
    ("TENAUR, s. r. o.", "26349451", "ano", "1204324.00"),
    ("TŠ JUST DANCE", "2655931", "ne", "160600.00"),
    ("Vodama technology s.r.o.", "19782292", "ano", "175150.00"),
]


def _ico(value):
    """IČO na 8 cifer - v obou zdrojích se vyskytuje bez vodicích nul
    (např. TŠ JUST DANCE '2655931'), takže se doplní zleva."""
    cislice = "".join(c for c in (value or "") if c.isdigit())
    return cislice.zfill(8) if cislice else ""


def _norm(name):
    """Název jen na písmena a číslice, bez diakritiky - záložní párování."""
    rozlozeno = unicodedata.normalize("NFKD", name or "")
    bez_diakritiky = "".join(c for c in rozlozeno if not unicodedata.combining(c))
    return "".join(c for c in bez_diakritiky.lower() if c.isalnum())


class Command(BaseCommand):
    help = "Porovná externí výpočet ročního nájmu a plátcovství DPH s naší DB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tolerance", type=float, default=1.0,
            help="Rozdíl v Kč, který se ještě považuje za shodu (výchozí 1).",
        )

    def handle(self, *args, **options):
        tolerance = Decimal(str(options["tolerance"]))

        # nase data: rocni najem za vsechny AKTIVNI karty klienta
        nase = {}
        for card in (
            ClientCard.objects.filter(is_active=True)
            .select_related("client")
            .prefetch_related("card_units__unit")
        ):
            rocne = sum(
                (
                    (cu.area_m2 or Decimal("0")) * (cu.rate_per_m2 or Decimal("0"))
                    for cu in card.card_units.all()
                ),
                Decimal("0"),
            )
            if rocne == 0:
                continue
            zaznam = nase.setdefault(
                card.client_id,
                {"client": card.client, "rocne": Decimal("0"), "karty": []},
            )
            zaznam["rocne"] += rocne
            zaznam["karty"].append((card, rocne))

        podle_ica = {}
        podle_nazvu = {}
        for zaznam in nase.values():
            c = zaznam["client"]
            if _ico(c.ico):
                podle_ica.setdefault(_ico(c.ico), zaznam)
            podle_nazvu.setdefault(_norm(c.name), zaznam)

        self.stdout.write(
            f"{'Klient (externí)':<36}{'Externí rok':>15}{'Naše rok':>15}{'Rozdíl':>13}  DPH"
        )
        self.stdout.write("-" * 100)

        pouzite = set()
        neshody_castka, neshody_dph, chybi_u_nas = [], [], []
        for nazev, ico, platce_txt, rocne_txt in EXTERNI:
            externi_rocne = Decimal(rocne_txt)
            externi_platce = platce_txt.strip().lower() == "ano"

            zaznam = podle_ica.get(_ico(ico)) or podle_nazvu.get(_norm(nazev))
            if zaznam is None:
                chybi_u_nas.append((nazev, ico, externi_rocne))
                self.stdout.write(
                    self.style.WARNING(
                        f"{nazev[:34]:<36}{externi_rocne:>15,.2f}{'—':>15}{'—':>13}  "
                        f"<- klient v naší DB nenalezen"
                    )
                )
                continue

            pouzite.add(zaznam["client"].id)
            nase_rocne = zaznam["rocne"]
            rozdil = nase_rocne - externi_rocne
            nas_platce = zaznam["client"].vat_payer

            dph_txt = "ANO" if nas_platce else "NE"
            if nas_platce != externi_platce:
                dph_txt = f"{'ANO' if externi_platce else 'NE'}→{dph_txt} NESEDÍ"
                neshody_dph.append((nazev, externi_platce, nas_platce))

            radek = (
                f"{nazev[:34]:<36}{externi_rocne:>15,.2f}{nase_rocne:>15,.2f}"
                f"{rozdil:>13,.2f}  {dph_txt}"
            )
            if abs(rozdil) > tolerance:
                neshody_castka.append((nazev, externi_rocne, nase_rocne, rozdil, zaznam))
                self.stdout.write(self.style.WARNING(radek + "  <- ČÁSTKA NESEDÍ"))
            elif "NESEDÍ" in dph_txt:
                self.stdout.write(self.style.WARNING(radek))
            else:
                self.stdout.write(radek)

        # co mame my navic
        navic = [z for cid, z in nase.items() if cid not in pouzite]

        self.stdout.write("-" * 100)
        ext_celkem = sum(Decimal(r[3]) for r in EXTERNI)
        nase_celkem = sum(
            z["rocne"] for cid, z in nase.items() if cid in pouzite
        )
        self.stdout.write(
            f"{'CELKEM (spárované)':<36}{ext_celkem:>15,.2f}{nase_celkem:>15,.2f}"
            f"{nase_celkem - ext_celkem:>13,.2f}"
        )

        if neshody_castka:
            self.stdout.write(self.style.WARNING(f"\n=== Rozdíly v částce ({len(neshody_castka)}) ==="))
            for nazev, ext, nase_r, rozdil, zaznam in neshody_castka:
                self.stdout.write(f"\n{nazev}: externě {ext:,.2f} / u nás {nase_r:,.2f} (rozdíl {rozdil:+,.2f})")
                for card, rocne in zaznam["karty"]:
                    self.stdout.write(f"   karta #{card.pk} „{card.description or '-'}“ -> {rocne:,.2f} Kč/rok")
                    for cu in card.card_units.all():
                        self.stdout.write(
                            f"      {cu.unit.name:<28} {cu.area_m2 or 0:>10,.2f} m² "
                            f"× {cu.rate_per_m2 or 0:>10,.2f} Kč/m²/rok"
                        )

        if neshody_dph:
            self.stdout.write(self.style.WARNING(f"\n=== Rozdíly v plátcovství DPH ({len(neshody_dph)}) ==="))
            for nazev, ext_p, nas_p in neshody_dph:
                self.stdout.write(
                    f"  {nazev}: externě {'plátce' if ext_p else 'neplátce'}, "
                    f"u nás {'plátce' if nas_p else 'neplátce'}"
                )

        if chybi_u_nas:
            self.stdout.write(self.style.WARNING(f"\n=== V naší DB nenalezeni ({len(chybi_u_nas)}) ==="))
            for nazev, ico, rocne in chybi_u_nas:
                self.stdout.write(f"  {nazev} (IČO {ico}) - externě {rocne:,.2f} Kč/rok")

        if navic:
            self.stdout.write(self.style.WARNING(f"\n=== Máme navíc, v externí tabulce nejsou ({len(navic)}) ==="))
            for z in sorted(navic, key=lambda z: z["client"].name):
                self.stdout.write(
                    f"  {z['client'].name} (IČO {z['client'].ico or '—'}) -> {z['rocne']:,.2f} Kč/rok"
                )

        if not (neshody_castka or neshody_dph or chybi_u_nas or navic):
            self.stdout.write(self.style.SUCCESS("\nVšechno sedí."))
