"""
Zakladni entity: arealy/objekty, pronajimane prostory, klienti
a jejich karty (najemni vztahy s platnosti).
"""
import calendar
import re
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models

from core.storage import R2MediaStorage


# Typy rozpoctu - sdileno mezi ServicePoolItem (vychozi typ) a AllocationKey
# (skutecny typ pouzity na konkretni karte klienta).
ALLOCATION_TYPE_CHOICES = [
    ("submeter", "Podružné měřidlo (1:1)"),
    ("fixed_amount", "Pevná částka"),
    ("weighted_count", "Podle váhy"),
    ("area_price", "Dle výměry (m²)"),
]


class Site(models.Model):
    """Areal nebo objekt (prumyslovy areal, bytovy dum...)."""

    name = models.CharField("Název", max_length=200)
    address = models.CharField("Adresa", max_length=300, blank=True)
    lease_subject_text = models.TextField(
        "Vymezení předmětu nájmu (text čl. 1 Smlouvy)", blank=True,
        help_text=(
            "Používá se při generování Smlouvy (core/contract_generator.py). "
            "První řádek je úvodní věta (katastrální úřad, LV, obec, k.ú.), "
            "každý další řádek je jeden pozemek/budova z výčtu."
        ),
    )

    class Meta:
        verbose_name = "Areál / objekt"
        verbose_name_plural = "Areály / objekty"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Unit(models.Model):
    """Pronajimany prostor v ramci arealu (kancelar, hala, byt...)."""

    site = models.ForeignKey(
        Site, on_delete=models.CASCADE, related_name="units", verbose_name="Areál"
    )
    name = models.CharField("Název / označení", max_length=200)
    area_m2 = models.DecimalField(
        "Výměra (m²)", max_digits=10, decimal_places=2, null=True, blank=True
    )
    description = models.CharField("Popis", max_length=300, blank=True)
    purpose = models.CharField("Účel", max_length=100, blank=True)
    rate_per_m2_year = models.DecimalField(
        "Sazba Kč/m²/rok", max_digits=10, decimal_places=2, null=True, blank=True
    )
    unit_type = models.CharField("Jednotka", max_length=10, blank=True, default="m2")

    class Meta:
        verbose_name = "Pronajímaný prostor"
        verbose_name_plural = "Pronajímané prostory"
        ordering = ["site", "name"]

    def __str__(self):
        return f"{self.site} – {self.name}"


class Client(models.Model):
    """Klient (najemce) - firma nebo osoba."""

    code = models.CharField("Kód", max_length=20, unique=True, blank=True)
    name = models.CharField("Název / jméno", max_length=200)
    is_active = models.BooleanField("Aktivní", default=True)
    is_landlord = models.BooleanField("Pronajímatel", default=False)

    street = models.CharField("Ulice", max_length=200, blank=True)
    street_number = models.CharField("Číslo", max_length=20, blank=True)
    zip_code = models.CharField("PSČ", max_length=10, blank=True)
    city = models.CharField("Město", max_length=100, blank=True)

    ico = models.CharField("IČO", max_length=20, blank=True)
    dic = models.CharField("DIČ", max_length=20, blank=True)
    vat_payer = models.BooleanField("Plátce DPH", default=False)

    class EntityType(models.TextChoices):
        LEGAL = "pravnicka", "Právnická osoba"
        NATURAL = "fyzicka", "Fyzická osoba"

    entity_type = models.CharField(
        "Typ osoby", max_length=20, blank=True, choices=EntityType.choices,
    )

    class RegistrySource(models.TextChoices):
        COMMERCIAL = "obchodni", "Obchodní rejstřík"
        TRADE = "zivnostensky", "Živnostenský rejstřík"

    registry_source = models.CharField(
        "Zdroj údajů", max_length=20, blank=True, choices=RegistrySource.choices,
        help_text="Ze kterého rejstříku pochází identifikační údaje klienta (IČO, sídlo...).",
    )

    class InsolvencyStatus(models.TextChoices):
        NONE = "", "—"
        ACTIVE = "aktivni", "Aktivní insolvenční řízení"
        HISTORICAL = "historicky", "Dřívější insolvenční řízení (uzavřeno)"

    insolvency_status = models.CharField(
        "Insolvenční rejstřík", max_length=20, blank=True,
        choices=InsolvencyStatus.choices,
        help_text=(
            "Vyplňuje se automaticky měsíční kontrolou proti ARES "
            "(core/management/commands/zkontrolovat_rizika.py) - neupravuj ručně."
        ),
    )

    registry_court = models.CharField(
        "Rejstříkový soud", max_length=100, blank=True,
        help_text="Např. 'Krajský soud v Ostravě' - lze dohledat/ověřit přes ARES podle IČO.",
    )
    registry_section = models.CharField("Oddíl", max_length=20, blank=True)
    registry_insert = models.CharField("Vložka", max_length=20, blank=True)

    representative_name = models.CharField(
        "Zástupce (jméno)", max_length=200, blank=True,
        help_text="Např. 'Ing. Daniel DAVID' - u Pronajímatele se použije jako podpis ve Smlouvě.",
    )
    representative_role = models.CharField(
        "Zástupce (funkce)", max_length=200, blank=True,
        help_text="Např. 'jediný člen představenstva' nebo 'jednatel'.",
    )

    bank_name = models.CharField("Banka", max_length=50, blank=True)
    bank_account = models.CharField("Číslo účtu", max_length=50, blank=True)
    bank_code = models.CharField("Kód banky", max_length=10, blank=True)

    contact_email = models.EmailField("E-mail", blank=True)
    contact_phone = models.CharField(
        "Telefon", max_length=50, blank=True, default="+420 ",
        help_text="Formát: +420 777123456.",
    )

    class Meta:
        verbose_name = "Klient"
        verbose_name_plural = "Klienti"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.is_landlord and Client.objects.filter(is_landlord=True).exclude(pk=self.pk).exists():
            raise ValidationError(
                "Pronajímatel může být v aplikaci nastaven jen jeden - odškrtni "
                "tento příznak u druhého klienta, který ho má aktuálně nastavený."
            )

    def save(self, *args, **kwargs):
        """Kdyz se klient prepne na neaktivniho, deaktivuji se i vsechny jeho
        (dosud aktivni) Karty - neaktivni klient nemuze mit aktivni kartu."""
        deactivate_cards = False
        if self.pk and not self.is_active:
            was_active = Client.objects.filter(pk=self.pk, is_active=True).exists()
            deactivate_cards = was_active
        super().save(*args, **kwargs)
        if deactivate_cards:
            self.cards.filter(is_active=True).update(is_active=False)


class Contract(models.Model):
    """Smlouva (najemni) uzavrena s klientem."""

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="contracts", verbose_name="Klient"
    )
    site = models.ForeignKey(
        Site, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="contracts", verbose_name="Areál",
        help_text="Potřeba pro záhlaví generovaného dokumentu smlouvy.",
    )
    number = models.CharField("Číslo smlouvy", max_length=50, blank=True)
    signed_on = models.DateField("Datum podpisu", null=True, blank=True)
    valid_from = models.DateField("Platnost od", null=True, blank=True)
    valid_to = models.DateField(
        "Platnost do", null=True, blank=True,
        help_text="Prázdné = na dobu neurčitou.",
    )
    notice_period_months = models.PositiveIntegerField(
        "Výpovědní lhůta (měsíce)", null=True, blank=True
    )

    deposit_czk = models.DecimalField(
        "Kauce (Kč)", max_digits=12, decimal_places=2, null=True, blank=True
    )
    deposit_paid = models.BooleanField("Kauce zaplacena", default=False)

    insurance_amount_czk = models.DecimalField(
        "Částka pojištění (Kč)", max_digits=12, decimal_places=2, null=True, blank=True
    )

    has_inflation_clause = models.BooleanField("Inflační doložka", default=False)
    inflation_increase_from = models.DateField(
        "Inflační navýšení platí od", null=True, blank=True,
        help_text="Jen pokud je zaškrtnutá inflační doložka.",
    )

    invoicing_email = models.EmailField(
        "E-mail pro elektronickou fakturaci", blank=True,
        help_text="Pokud se liší od kontaktního e-mailu klienta.",
    )

    representative_name = models.CharField("Zastupuje (jméno)", max_length=200, blank=True)
    representative_role = models.CharField(
        "Zastupuje (funkce)", max_length=100, blank=True,
        help_text="Např. 'jednatel', 'na základě plné moci'.",
    )

    document = models.FileField(
        "Vygenerovaný dokument", upload_to="smlouvy/", null=True, blank=True
    )
    note = models.TextField("Poznámka", blank=True)

    class Meta:
        verbose_name = "Smlouva"
        verbose_name_plural = "Smlouvy"
        ordering = ["-valid_from"]

    def __str__(self):
        return ""


class ClientCard(models.Model):
    """Karta klienta - vazba klienta na konkretni pronajaty prostor s obdobim platnosti."""

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="cards", verbose_name="Klient"
    )
    unit = models.ForeignKey(
        Unit, on_delete=models.SET_NULL, related_name="cards", verbose_name="Prostor",
        null=True, blank=True
    )
    valid_from = models.DateField("Platnost od")
    valid_to = models.DateField("Platnost do", null=True, blank=True)
    note = models.CharField("Poznámka", max_length=300, blank=True)
    external_id = models.IntegerField("Původní ID (IDK)", null=True, blank=True)
    description = models.CharField("Popis karty", max_length=200, blank=True)
    is_active = models.BooleanField("Aktivní", default=True)
    document = models.FileField(
        "Vygenerovaný dokument (Karta nájemce)", upload_to="karty/", null=True, blank=True
    )
    po_number_rent = models.CharField(
        "Číslo objednávky - nájemné", max_length=100, blank=True,
        help_text="Někteří klienti vyžadují uvést na faktuře za nájemné - vázané na tuto Kartu.",
    )
    po_number_services = models.CharField(
        "Číslo objednávky - energie a služby", max_length=100, blank=True,
        help_text="Někteří klienti vyžadují uvést na faktuře/vyúčtování za energie a služby - vázané na tuto Kartu.",
    )

    class Meta:
        verbose_name = "Karta klienta"
        verbose_name_plural = "Karty klientů"
        ordering = ["client", "valid_from"]

    def __str__(self):
        return ""

    def save(self, *args, **kwargs):
        """Pokud Popis karty neni vyplneny, dopocita se ve formatu "Karta
        {kod klienta} {rok platnosti} - {poradi karty klienta v tom
        roce}" - stejna konvence, jakou uz maji stavajici karty z
        importu (napr. "Karta ANDELE 2026 - 1"), aby ji Daniel nemusel
        pri zakladani nove karty psat rucne."""
        if not self.description and self.client_id and self.valid_from:
            year = self.valid_from.year
            order = ClientCard.objects.filter(
                client_id=self.client_id, valid_from__year=year
            ).exclude(pk=self.pk).count() + 1
            self.description = f"Karta {self.client.code} {year} - {order}"
        super().save(*args, **kwargs)

    def clean(self):
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError("Datum 'platnost do' nesmí být dříve než 'platnost od'.")
        if self.is_active:
            conflict = self.active_card_conflict()
            if conflict:
                raise ValidationError(
                    f"Klient {self.client} už má aktivní kartu ve stejném areálu: "
                    f"{conflict.description}. Nejprve deaktivujte stávající kartu."
                )

    def sites(self):
        """Arealy, do kterych karta zasahuje - podle ulozenych Ploch (CardUnit)."""
        return Site.objects.filter(units__card_units__card_id=self.pk).distinct()

    def active_card_conflict(self):
        """Vrati jinou aktivni kartu stejneho klienta ve stejnem arealu, pokud
        existuje - jinak None. Areal karty se pozna jen podle jiz ulozenych
        Ploch (CardUnit), takze u nove karty bez ulozenych ploch (self.pk je
        None, nebo karta jeste zadne Plochy nema) konflikt zjistit nejde -
        zkontroluje se az pri pristim ulozeni, kdy uz Plochy existuji."""
        if not self.pk:
            return None
        my_sites = set(self.sites())
        if not my_sites:
            return None
        others = ClientCard.objects.filter(client_id=self.client_id, is_active=True).exclude(pk=self.pk)
        for other in others:
            if my_sites & set(other.sites()):
                return other
        return None

    def active_days_in_period(self, period_start, period_end):
        start = max(self.valid_from, period_start)
        end = min(self.valid_to or period_end, period_end)
        if end < start:
            return 0
        return (end - start).days + 1

    def create_exact_copy(self, client=None, valid_from=None, is_active=False):
        """Vytvori presnou kopii teto karty (plochy i klice 1:1 z originalu).
        Zamerne NEPOUZIVA CardUnit.save()/create_default_keys() (ktere by
        klice odvozovaly znovu z vychozich sluzeb plochy - UnitService) -
        misto toho se kazdy AllocationKey originalu zkopiruje presne tak,
        jak je (vc. pripadnych rucnich uprav hodnoty/mericí)."""
        units = list(self.card_units.all())
        keys = list(self.allocation_keys.all())

        new_card = ClientCard(
            client=client or self.client,
            unit=self.unit,
            valid_from=valid_from or self.valid_from,
            valid_to=self.valid_to,
            note=self.note,
            description=f"{self.description} (kopie)",
            external_id=None,
            is_active=is_active,
        )
        new_card.save()

        CardUnit.objects.bulk_create([
            CardUnit(
                card=new_card, unit=cu.unit,
                rate_per_m2=cu.rate_per_m2, area_m2_override=cu.area_m2_override,
            )
            for cu in units
        ])
        AllocationKey.objects.bulk_create([
            AllocationKey(
                client_card=new_card,
                service_item=key.service_item,
                allocation_type=key.allocation_type,
                value=key.value,
                meter=key.meter,
                unit=key.unit,
                deduct_from_pool=key.deduct_from_pool,
                valid_from=key.valid_from,
                valid_to=key.valid_to,
            )
            for key in keys
        ])
        return new_card


class Period(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Otevřeno"
        CLOSED = "closed", "Uzavřeno"

    year = models.PositiveIntegerField("Rok")
    month = models.PositiveSmallIntegerField("Měsíc")
    status = models.CharField("Stav", max_length=10, choices=Status.choices, default=Status.OPEN)

    class Meta:
        verbose_name = "Období"
        verbose_name_plural = "Období"
        unique_together = ("year", "month")
        ordering = ["-year", "-month"]

    def __str__(self):
        return f"{self.month:02d}/{self.year}"

    def date_range(self):
        first_day = date(self.year, self.month, 1)
        last_day_num = calendar.monthrange(self.year, self.month)[1]
        last_day = date(self.year, self.month, last_day_num)
        return first_day, last_day

    @property
    def days_in_period(self):
        first_day, last_day = self.date_range()
        return (last_day - first_day).days + 1

    def previous_period(self):
        if self.month == 1:
            prev_year, prev_month = self.year - 1, 12
        else:
            prev_year, prev_month = self.year, self.month - 1
        return Period.objects.filter(year=prev_year, month=prev_month).first()


class InflationRate(models.Model):
    """Mira inflace pro dany rok - pouziva se pri hromadnem generovani
    novych Karet klientu se smlouvou s inflacni dolozkou (viz
    ContractAdmin.generovat_karty_inflace)."""

    year = models.PositiveIntegerField("Rok", unique=True)
    percent = models.DecimalField("Míra inflace (%)", max_digits=5, decimal_places=2)

    class Meta:
        verbose_name = "Míra inflace"
        verbose_name_plural = "Míry inflace"
        ordering = ["-year"]

    def __str__(self):
        return f"{self.year}: {self.percent} %"


class Meter(models.Model):
    class MeterType(models.TextChoices):
        ELECTRICITY = "electricity", "Elektřina"
        WATER = "water", "Voda"
        GAS = "gas", "Plyn"
        HEAT = "heat", "Teplo"
        OTHER = "other", "Jiné"

    class ReadingMode(models.TextChoices):
        STATE = "state", "Stavy (kumulativní odečet, spotřeba = rozdíl mezi obdobími)"
        CONSUMPTION = "consumption", "Spotřeba za období (dodavatel hlásí rovnou spotřebu, ne stav)"

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="meters", verbose_name="Areál")
    parent_meter = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="children", verbose_name="Nadřazené měřidlo"
    )
    code = models.CharField(
        "Kód", max_length=50, blank=True,
        help_text="Krátký kód pro odkazování ve vzorcích virtuálních měřičů (např. E_A1).",
    )
    name = models.CharField("Název / označení", max_length=200)
    meter_type = models.CharField("Typ", max_length=20, choices=MeterType.choices)
    unit_of_measure = models.CharField("Měrná jednotka", max_length=20, default="kWh")
    reading_mode = models.CharField(
        "Způsob zadávání odečtů", max_length=20, choices=ReadingMode.choices, default=ReadingMode.STATE,
        help_text=(
            "Většina měřidel hlásí kumulativní Stav (spotřeba se dopočítá jako "
            "rozdíl vůči minulému období). Pokud dodavatel hlásí rovnou Spotřebu "
            "za období (např. hlavní odběrné místo elektro), přepni na tento režim "
            "- pak stačí zadat odečet jen za aktuální období, hodnota se použije přímo."
        ),
    )
    serial_number = models.CharField("Výrobní číslo", max_length=100, blank=True)
    is_virtual = models.BooleanField(
        "Virtuální (vypočtené)", default=False,
        help_text="Spotřeba se nepočítá z odečtů, ale ze vzorce odkazujícího na jiná měřidla (pole Vzorec).",
    )
    formula = models.CharField(
        "Vzorec", max_length=300, blank=True,
        help_text="Pouze pro virtuální měřidla, např. E_A1+E_AB1 (kódy jiných měřidel).",
    )
    weight_unit_label = models.CharField(
        "Co je váhou (u klíčů 'Podle váhy' na tomto měřidle)", max_length=100, blank=True,
        help_text=(
            "Krátký popis, co hodnota Klíče typu 'Podle váhy' napojeného na "
            "toto měřidlo znamená - např. 'm2', 'počet osob', 'počet "
            "radiátorů'. Typické pro virtuální 'zbytková' měřidla jako "
            "E_SPOL, kde se jejich spotřeba dělí mezi více karet vahou. Jen "
            "informativní (zobrazuje se v adminu a v Kartě klienta), na "
            "samotný výpočet nemá vliv."
        ),
    )
    display_order = models.PositiveIntegerField(
        "Pořadí při zadávání odečtů", default=0,
        help_text="Určuje pořadí měřidel na obrazovce pro zadávání odečtů. Stejná hodnota (výchozí 0) řadí abecedně podle kódu.",
    )

    class Meta:
        verbose_name = "Měřidlo"
        verbose_name_plural = "Měřidla"
        ordering = ["site", "meter_type", "code"]

    def __str__(self):
        return self.code or self.name

    def consumption_for(self, period, readings_cache=None):
        """`readings_cache`: volitelny dict {(meter_id, period_id):
        MeterReading} pro hromadne predem nactene odecty (viz
        billing/engine.py calculate_period) - misto dvou samostatnych
        DB dotazu (aktualni + predchozi obdobi) na KAZDE meridlo se
        pouzije uz nacteny objekt z pameti. Bez cache (vychozi, vsechny
        ostatni volajici - admin, reporty, diagnosticke prikazy) se
        chova uplne stejne jako drive."""
        if self.is_virtual:
            return self._formula_consumption_for(period, readings_cache=readings_cache)

        if readings_cache is not None:
            current = readings_cache.get((self.id, period.id))
        else:
            current = self.readings.filter(period=period).first()
        if current is None:
            return None

        if self.reading_mode == self.ReadingMode.CONSUMPTION:
            # Dodavatel hlasi rovnou spotrebu za obdobi - zadana hodnota
            # se pouzije primo, neni potreba znat predchozi obdobi.
            return current.value

        if current.reset_from_value is not None:
            # Vymena meridla - stary a novy pristroj nejsou kontinualni,
            # spotreba se pocita od pocatecniho stavu noveho meridla, ne
            # od minuleho odectu (ktery patril jeste staremu pristroji).
            return current.value - current.reset_from_value

        prev_period = period.previous_period()
        if prev_period is None:
            return None
        if readings_cache is not None:
            previous = readings_cache.get((self.id, prev_period.id))
        else:
            previous = self.readings.filter(period=prev_period).first()
        if previous is None:
            return None
        return current.value - previous.value

    def _formula_tokens(self):
        """Rozparsuje pole Vzorec na seznam (meridlo, znamenko) dvojic -
        sdileno mezi _formula_consumption_for (vypocet) a consumption_leaves
        (zobrazeni rozpadu na jednotliva realna meridla v auditovaci
        tabulce, viz billing/key_detail.py)."""
        if not self.formula:
            return []
        tokens = re.findall(r"[+-]?[^+-]+", self.formula)
        result = []
        for raw_token in tokens:
            token = raw_token.strip()
            sign = 1
            if token.startswith("-"):
                sign = -1
                token = token[1:].strip()
            elif token.startswith("+"):
                token = token[1:].strip()
            if not token:
                continue
            meter = Meter.objects.filter(site=self.site, code=token).first()
            if meter is None:
                continue
            result.append((meter, sign))
        return result

    def _formula_consumption_for(self, period, readings_cache=None):
        """Vyhodnoti pole Vzorec, napr. '668NT+668VT' - secte/odecte
        spotrebu jinych mericí stejneho arealu podle jejich kodu."""
        total = None
        for meter, sign in self._formula_tokens():
            value = meter.consumption_for(period, readings_cache=readings_cache)
            if value is None:
                continue
            signed_value = sign * value
            total = signed_value if total is None else total + signed_value
        return total

    def consumption_leaves(self, sign=1):
        """Rekurzivne rozbali virtualni meridlo (vcetne vnorenych vzorcu) az
        na (realne_meridlo, znamenko) dvojice - realne meridlo vrati samo
        sebe. Pouziva se jen pro zobrazeni rozpadu spotreby na jednotliva
        fyzicka meridla v auditovaci tabulce (billing/key_detail.py), na
        skutecny vypocet (consumption_for) nema vliv."""
        if not self.is_virtual:
            return [(self, sign)]
        leaves = []
        for sub_meter, sub_sign in self._formula_tokens():
            leaves.extend(sub_meter.consumption_leaves(sign=sign * sub_sign))
        return leaves


class MeterReading(models.Model):
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name="readings", verbose_name="Měřidlo")
    period = models.ForeignKey(Period, on_delete=models.CASCADE, related_name="readings", verbose_name="Období")
    reading_date = models.DateField("Datum odečtu")
    value = models.DecimalField(
        "Stav / spotřeba", max_digits=14, decimal_places=3,
        help_text="Podle nastavení měřidla: buď kumulativní stav, nebo rovnou spotřeba za období.",
    )
    note = models.CharField("Poznámka", max_length=300, blank=True)
    photo = models.ImageField(
        "Foto odečtu", upload_to="odecty/%Y/%m/", null=True, blank=True,
        storage=R2MediaStorage(),
    )
    reset_from_value = models.DecimalField(
        "Počáteční stav (výměna měřidla)", max_digits=14, decimal_places=3, null=True, blank=True,
        help_text=(
            "Vyplnit jen při výměně měřidla za nové - stav v poli 'Stav / "
            "spotřeba' pak patří novému přístroji a spotřeba se počítá od "
            "tohoto počátečního stavu (obvykle 0), ne od minulého odečtu "
            "starého měřidla. Viz Meter.consumption_for."
        ),
    )

    class Meta:
        verbose_name = "Odečet měřidla"
        verbose_name_plural = "Odečty měřidel"
        unique_together = ("meter", "period")
        ordering = ["-period", "meter"]

    def __str__(self):
        return f"{self.meter} – {self.period}: {self.value}"

    _tracked_fields = ("period_id", "reading_date", "value", "note", "reset_from_value")

    def clean(self):
        if self.period_id and self.period.status == Period.Status.CLOSED and self._reading_data_changed():
            raise ValidationError("Období je uzavřené, odečet nejde přidat ani upravit.")

    def _reading_data_changed(self):
        """True pro novy odecet nebo pokud se u existujiciho zmenil nektery
        z udaju o odectu samotnem. Bez tohohle by se saved formulare s
        MeterReadingInline (napr. jen oprava nazvu Meridla) nesly ulozit,
        jakmile ma mericlo aspon jeden odecet ve zminulem uzavrenem obdobi -
        Django validuje pri ukladani vsechny radky inline, i nezmenene."""
        if not self.pk:
            return True
        original = MeterReading.objects.filter(pk=self.pk).values(*self._tracked_fields).first()
        if original is None:
            return True
        return any(original[field] != getattr(self, field) for field in self._tracked_fields)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class ServicePoolItem(models.Model):
    class InvoiceClass(models.TextChoices):
        RENT = "rent", "Nájemné"
        ELECTRICITY = "electricity", "Elektřina"
        WATER = "water", "Voda"
        HEAT = "heat", "Teplo"
        OTHER = "other", "Ostatní"

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="service_items", verbose_name="Areál")
    unit = models.ForeignKey(
        Unit, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="service_items", verbose_name="Prostor"
    )
    meter = models.ForeignKey(
        Meter, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="service_items", verbose_name="Měřidlo"
    )
    name = models.CharField("Název", max_length=200)
    invoice_class = models.CharField(
        "Třída", max_length=20, choices=InvoiceClass.choices, default=InvoiceClass.OTHER
    )
    default_allocation_type = models.CharField(
        "Výchozí typ rozpočtu", max_length=20, choices=ALLOCATION_TYPE_CHOICES, blank=True,
        help_text="Předvyplní se při založení nového klíče na kartě klienta pro tuto položku.",
    )
    default_amount_czk = models.DecimalField(
        "Výchozí měsíční částka (Kč)", max_digits=12, decimal_places=2, null=True, blank=True,
        help_text=(
            "Použije se při výpočtu rozúčtování pro období, pro které není "
            "zadaný žádný Náklad za období (CostEntry) - typicky pro služby "
            "s neměnnou paušální cenou (ostraha, internet...), aby se nemusela "
            "částka zadávat každý měsíc ručně. Pokud je pro dané období CostEntry "
            "zadaný, má vždy přednost před touto výchozí částkou."
        ),
    )
    weight_unit_label = models.CharField(
        "Co je váhou (u klíčů 'Podle váhy' bez vlastního měřidla)", max_length=100, blank=True,
        help_text=(
            "Krátký popis, co hodnota Klíče typu 'Podle váhy' na téhle "
            "položce znamená - např. 'm2', 'počet osob'. Použije se jen "
            "u klíčů BEZ vlastního napojeného měřidla (ty mají přednost "
            "Meter.weight_unit_label - jedna položka může mít víc "
            "různých vážených skupin s různým významem váhy, např. "
            "'hlavní odběr elektro FM'). Jen informativní, na samotný "
            "výpočet nemá vliv."
        ),
    )

    class Meta:
        verbose_name = "Položka zásobníku"
        verbose_name_plural = "Zásobník"
        ordering = ["site", "invoice_class", "name"]

    def __str__(self):
        return f"{self.name} ({self.site})"


class AllocationKey(models.Model):
    class AllocationType(models.TextChoices):
        SUBMETER = "submeter", "Podružné měřidlo (1:1)"
        FIXED_AMOUNT = "fixed_amount", "Pevná částka"
        WEIGHTED_COUNT = "weighted_count", "Podle váhy"
        AREA_PRICE = "area_price", "Dle výměry (m²)"

    client_card = models.ForeignKey(
        ClientCard, on_delete=models.CASCADE, related_name="allocation_keys", verbose_name="Karta klienta"
    )
    service_item = models.ForeignKey(
        ServicePoolItem, on_delete=models.CASCADE, related_name="allocation_keys", verbose_name="Položka zásobníku"
    )
    allocation_type = models.CharField("Typ rozpočtu", max_length=20, choices=AllocationType.choices)
    value = models.DecimalField(
        "Hodnota", max_digits=12, decimal_places=4, null=True, blank=True,
        help_text=(
            "Význam závisí na typu: u 'Pevná částka' jde o hotovou Kč částku/měsíc, "
            "u 'Dle výměry (m2)' jde o výměru v m2 (cena/m2/rok se bere z Ceníku "
            "položky pro dané období), u 'Podružné měřidlo' se použije jen pokud "
            "stejné měřidlo sdílí více karet - pak jde o váhu pro rozdělení jeho "
            "spotřeby mezi ně (u jedné karty na měřidlo se nepoužije, dostane celou "
            "spotřebu). U 'Podle váhy' jde o libovolné relativní číslo vyjadřující "
            "podíl na společném nákladu (m2, počet osob, počet kusů, radiátorů "
            "apod. - jednotka záleží na tom, jak položka danou spotřebu/náklad "
            "rozpočítává) - systém ho vždy normalizuje tak, aby součet všech karet "
            "dal dohromady 100 %, stačí tedy zadat správný POMĚR mezi kartami."
        ),
    )
    meter = models.ForeignKey(
        Meter, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="submeter_keys", verbose_name="Podružné měřidlo"
    )
    unit = models.ForeignKey(
        Unit, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="allocation_keys", verbose_name="Plocha",
        help_text=(
            "U klíčů založených automaticky přes CardUnit.create_default_keys() "
            "(přidání Plochy na Kartu) označuje, ze které konkrétní Plochy klíč "
            "vznikl - podle toho se smaže spolu s ní (viz CardUnit.delete()). "
            "U ručně založených nebo importovaných klíčů (napr. součet více "
            "ploch karty, srážkové vody) zůstává prázdné - jejich mazání se "
            "s žádnou Plochou automaticky neváže."
        ),
    )
    deduct_from_pool = models.BooleanField(
        "Odečíst z celkového nákladu",
        default=True,
        help_text=(
            "Jen pro typ 'Pevná částka' a 'Plocha × cena/m²'. Pokud ANO (výchozí): tato "
            "částka se odečte od celkového nákladu položky a zbytek se rozpočítá ostatním "
            "kartám podle jejich klíčů (klient reálně snižuje sdílený náklad, napr. mel jiz "
            "vlastni smlouvu). Pokud NE: klient zaplatí částku samostatně/navíc a celkový "
            "náklad se mezi ostatní karty rozpočítá beze změny (typicky pausál, ktery "
            "nesouvisí se sdílenym meridlem - napr. teplo bez pripojeni na hlavni odber)."
        ),
    )
    valid_from = models.DateField(
        "Platnost od", null=True, blank=True,
        help_text="Volitelné - typicky se platnost řeší na úrovni celé Karty klienta.",
    )
    valid_to = models.DateField("Platnost do", null=True, blank=True)
    is_billed = models.BooleanField(
        "Fakturovat", default=True,
        help_text=(
            "Odpovídá sloupci 'FinTok' v původních Excel tabulkách klíčů. Pokud NE: "
            "částka se i tak započítá do výpočtu (spravedlivě snižuje podíl ostatních "
            "karet na sdíleném nákladu), ale klientovi se samostatně NEFAKTURUJE - "
            "typicky proto, že už ji má zahrnutou v paušální platbě (nájem + energie "
            "dohromady). Promítá se do BillingLine.is_billed a do klientského PDF "
            "vyúčtování (billing/statement_generator.py)."
        ),
    )

    class Meta:
        verbose_name = "Klíč"
        verbose_name_plural = "Klíče"
        ordering = ["service_item", "client_card"]

    def __str__(self):
        return ""

    @property
    def weight_unit_label(self):
        """Popisek 'Co je váhou' pro typ 'Podle váhy' - meridlo (pokud je
        napojene a ma vlastni popisek) ma prednost pred polozkou (viz
        ServicePoolItem.weight_unit_label help_text - jedna polozka muze
        mit vic ruznych vazenych skupin s ruznym vyznamem vahy)."""
        if self.meter_id and self.meter.weight_unit_label:
            return self.meter.weight_unit_label
        return self.service_item.weight_unit_label

    def is_valid_for_period(self, period):
        if not self.client_card.is_active:
            return False
        period_start, period_end = period.date_range()
        if self.valid_from and self.valid_from > period_end:
            return False
        if self.valid_to and self.valid_to < period_start:
            return False
        return True


class PriceList(models.Model):
    """
    Ceník - cena za jednotku pro danou položku zásobníku v daném období.
    Pokud pro aktuální období ceník neexistuje, použije se poslední platný
    (viz metoda get_price_for_period) - není tedy nutné zadávat každý měsíc.
    """
    service_item = models.ForeignKey(
        ServicePoolItem, on_delete=models.CASCADE,
        related_name="price_list", verbose_name="Položka zásobníku"
    )
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE,
        related_name="price_list", verbose_name="Období"
    )
    price_per_unit = models.DecimalField(
        "Cena za jednotku (Kč)", max_digits=12, decimal_places=4
    )
    note = models.CharField("Poznámka", max_length=300, blank=True)

    class Meta:
        verbose_name = "Ceník"
        verbose_name_plural = "Ceníky"
        unique_together = ("service_item", "period")
        ordering = ["-period", "service_item"]

    def __str__(self):
        return f"{self.service_item} – {self.period}: {self.price_per_unit} Kč/j"

    @classmethod
    def get_price_for_period(cls, service_item, period, price_cache=None):
        """
        Vrátí cenu za jednotku pro dané nebo nejbližší předchozí období.

        `price_cache`: volitelny dict {service_item_id: [PriceList
        serazene sestupne dle obdobi]} pro hromadne predem nactene
        ceniky (viz billing/engine.py calculate_period) - misto
        samostatneho DB dotazu na KAZDE volani se "posledni platna
        cena k datu" dohleda v pameti. Bez cache (vychozi) se chova
        uplne stejne jako drive."""
        if price_cache is not None:
            for pl in price_cache.get(service_item.id, []):
                if (pl.period.year, pl.period.month) <= (period.year, period.month):
                    return pl.price_per_unit
            return None
        entry = cls.objects.filter(
            service_item=service_item,
        ).filter(
            models.Q(period__year__lt=period.year) |
            models.Q(period__year=period.year, period__month__lte=period.month)
        ).order_by("-period__year", "-period__month").first()
        return entry.price_per_unit if entry else None


class CostEntry(models.Model):
    """
    Náklady/spotřeba za období.

    Pro MĚŘENÉ služby (energie):
      - amount_units = fakturované množství od dodavatele (kWh, m³, GJ...)
      - amount_czk nechat prázdné - Kč se vypočítá přes PriceList
    Pro NEMĚŘENÉ služby (úklid, ostraha...):
      - amount_czk = přímá fakturovaná částka v Kč
      - amount_units nechat prázdné
    """
    NOTE_K_DOPLNENI = "K DOPLNĚNÍ"
    service_item = models.ForeignKey(
        ServicePoolItem, on_delete=models.CASCADE,
        related_name="cost_entries", verbose_name="Položka zásobníku"
    )
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE,
        related_name="cost_entries", verbose_name="Období"
    )
    amount_units = models.DecimalField(
        "Fakturované množství (jednotky)",
        max_digits=14, decimal_places=3,
        null=True, blank=True,
        help_text="Pro měřené služby: kWh, m³, GJ... od dodavatele.",
    )
    amount_czk = models.DecimalField(
        "Částka (Kč)",
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        help_text="Pro neměřené služby: přímá fakturovaná částka v Kč.",
    )
    note = models.CharField("Poznámka", max_length=300, blank=True)

    class Meta:
        verbose_name = "Náklad za období"
        verbose_name_plural = "Náklady za období"
        unique_together = ("service_item", "period")
        ordering = ["-period", "service_item"]

    def __str__(self):
        if self.amount_units is not None:
            return f"{self.service_item} – {self.period}: {self.amount_units} j"
        return f"{self.service_item} – {self.period}: {self.amount_czk} Kč"

    def clean(self):
        """0 v amount_units/amount_czk NENÍ totéž co prázdné pole -
        get_amount_czk() bere `is not None`, takže amount_czk=0 by se
        vzalo jako skutečná (a konečná) nulová částka a amount_units by
        se vůbec nepoužilo - položka by se klientům potichu vyúčtovala
        na 0 Kč. Kdo nemá pro tenhle záznam částku/množství, ať pole
        nechá prázdné, ne 0 (viz konverzace s Danielem)."""
        if self.amount_units == 0:
            raise ValidationError({
                "amount_units": (
                    "Nezadávej 0 - pokud tahle položka fakturované množství nemá, "
                    "nech pole prázdné."
                )
            })
        if self.amount_czk == 0:
            raise ValidationError({
                "amount_czk": (
                    "Nezadávej 0 - Kč se buď dopočítá z jednotek přes Ceník, nebo "
                    "sem zadej skutečnou fakturovanou částku. Nech pole prázdné, "
                    "pokud přímou částku nezadáváš."
                )
            })

    def save(self, *args, **kwargs):
        """Jakmile se doplni amount_units nebo amount_czk, sama zmizi
        znacka NOTE_K_DOPLNENI (viz core/admin.py
        PeriodAdmin.vygenerovat_chybejici_naklady) - jinak by v Poznamce
        zustavala navzdy, i kdyz uz zaznam neni "k doplneni", a matla by
        pozdejsi hledani/filtr Stav=Nevyplneno."""
        if self.note == self.NOTE_K_DOPLNENI and (self.amount_units is not None or self.amount_czk is not None):
            self.note = ""
        super().save(*args, **kwargs)

    def get_amount_czk(self, period=None, price_cache=None):
        """Vrátí částku v Kč - buď přímo, nebo přes ceník.

        `price_cache`: viz PriceList.get_price_for_period - predano dal
        beze zmeny."""
        if self.amount_czk is not None:
            return self.amount_czk
        if self.amount_units is not None:
            p = period or self.period
            price = PriceList.get_price_for_period(self.service_item, p, price_cache=price_cache)
            if price:
                return self.amount_units * price
        return None


class BillingLine(models.Model):
    client_card = models.ForeignKey(
        ClientCard, on_delete=models.CASCADE, related_name="billing_lines", verbose_name="Karta klienta"
    )
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, related_name="billing_lines", verbose_name="Období"
    )
    service_item = models.ForeignKey(
        ServicePoolItem, on_delete=models.CASCADE, related_name="billing_lines", verbose_name="Položka zásobníku"
    )
    amount = models.DecimalField("Částka (Kč)", max_digits=14, decimal_places=2)
    units = models.DecimalField(
        "Množství (jednotky)", max_digits=14, decimal_places=3,
        null=True, blank=True,
        help_text="Přidělené jednotky (kWh, m³...) včetně poměrných ztrát.",
    )
    share = models.DecimalField("Podíl", max_digits=8, decimal_places=6, null=True, blank=True)
    calc_detail = models.JSONField("Detail výpočtu", default=dict, blank=True)
    is_billed = models.BooleanField(
        "Fakturováno klientovi", default=True,
        help_text=(
            "Snímek AllocationKey.is_billed v okamžiku výpočtu (viz billing/engine.py) - "
            "částka se počítala do rozpočtu vždy, ale pokud NE, klientovi se v PDF "
            "vyúčtování nepřipočítá do částky k úhradě (už ji má v paušálu)."
        ),
    )

    class Meta:
        verbose_name = "Vyúčtovaná položka"
        verbose_name_plural = "Vyúčtované položky"
        unique_together = ("client_card", "period", "service_item")
        ordering = ["-period", "client_card", "service_item"]

    def __str__(self):
        return f"{self.client_card} – {self.service_item} – {self.period}: {self.amount} Kč"

    @property
    def invoice_class(self):
        return self.service_item.invoice_class


class CardUnit(models.Model):
    """Vazba karty klienta na plochu - karta může mít více ploch."""

    card = models.ForeignKey(
        ClientCard, on_delete=models.CASCADE, related_name="card_units", verbose_name="Karta"
    )
    unit = models.ForeignKey(
        Unit, on_delete=models.CASCADE, related_name="card_units", verbose_name="Plocha"
    )
    rate_per_m2 = models.DecimalField(
        "Cena Kč/m²/rok", max_digits=10, decimal_places=2, null=True, blank=True
    )
    area_m2_override = models.DecimalField(
        "Výměra (m²) - úprava",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Vyplnit jen pokud se liší od výměry v zásobníku (např. pronajatá část plochy).",
    )

    class Meta:
        verbose_name = "Plocha karty"
        verbose_name_plural = "Plochy karty"
        unique_together = ("card", "unit")

    def __str__(self):
        return ""

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self.create_default_keys()

    def delete(self, *args, **kwargs):
        """Smaze i Klice vznikle z teto Plochy (viz create_default_keys -
        pozna se podle AllocationKey.unit=tato Plocha). Pokud stejnou
        polozku ma i jina Plocha karty, jeji vlastni klic zustava
        needotceny (kazda Plocha ma od 2026-08 svuj VLASTNI klic, ne
        sdileny/scitany - viz konverzace s Danielem, scitani resi az
        samostatna funkce Konsolidace)."""
        AllocationKey.objects.filter(client_card=self.card, unit=self.unit).delete()
        super().delete(*args, **kwargs)

    def create_default_keys(self):
        """Kazda Plocha si vytvori VLASTNI Klice (uz ne get_or_create
        sdileny s jinou Plochou stejne karty pro stejnou polozku - to
        drive znamenalo, ze druha Plocha se stejnou polozkou svou
        hodnotu proste ztratila, nic se nesecetlo). Karta tak muze mit
        vic klicu se stejnou polozkou/typem najednou - billing/engine.py
        je pro vazene i pevne typy stejne SECTE pri vypoctu (kazdy klic
        pricte svou hodnotu do stejneho client_card_id), takze na vysledek
        to nema vliv, jen na prehlednost v adminu - tu resi Konsolidace.
        `unit=self.unit` oznacuje, ze klic vznikl z TETO Plochy, aby ho
        slo smazat spolu s ni (viz delete() vyse)."""
        for unit_service in self.unit.unit_services.all():
            if unit_service.allocation_type == AllocationKey.AllocationType.AREA_PRICE:
                # Hodnota klice = skutecna vymera teto plochy na karte (vc.
                # pripadneho area_m2_override), ne rucne zadana hodnota v
                # UnitService - cena/m2 se pak bere z Ceniku polozky.
                value = self.area_m2
            else:
                value = unit_service.value
            AllocationKey.objects.create(
                client_card=self.card,
                service_item=unit_service.service_item,
                meter=unit_service.meter,
                unit=self.unit,
                allocation_type=unit_service.allocation_type,
                value=value,
            )

    @property
    def area_m2(self):
        if self.area_m2_override is not None:
            return self.area_m2_override
        return self.unit.area_m2

    @property
    def monthly_rent(self):
        if self.rate_per_m2 and self.area_m2:
            return round(self.area_m2 * self.rate_per_m2 / 12, 2)
        return None


class UnitService(models.Model):
    """
    Výchozí služby přiřazené k ploše - při přidání plochy na kartu
    se automaticky vytvoří klíče pro tyto služby.
    """

    unit = models.ForeignKey(
        Unit, on_delete=models.CASCADE, related_name="unit_services", verbose_name="Plocha"
    )
    service_item = models.ForeignKey(
        ServicePoolItem, on_delete=models.CASCADE, related_name="unit_services", verbose_name="Služba"
    )
    allocation_type = models.CharField(
        "Typ rozpočtu", max_length=20,
        choices=AllocationKey.AllocationType.choices,
        default=AllocationKey.AllocationType.SUBMETER
    )
    value = models.DecimalField(
        "Hodnota", max_digits=12, decimal_places=4, null=True, blank=True
    )
    meter = models.ForeignKey(
        Meter, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="unit_services", verbose_name="Měřidlo"
    )

    class Meta:
        verbose_name = "Výchozí služba plochy"
        verbose_name_plural = "Výchozí služby plochy"
        unique_together = ("unit", "service_item", "meter")

    def __str__(self):
        return ""
