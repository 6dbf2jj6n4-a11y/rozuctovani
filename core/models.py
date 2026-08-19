"""
Zakladni entity: arealy/objekty, pronajimane prostory, klienti
a jejich karty (najemni vztahy s platnosti).
"""
import calendar
import re
from datetime import date
from decimal import Decimal

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
    is_residential = models.BooleanField(
        "Bytový prostor", default=False,
        help_text=(
            "Zapnuto = bytový prostor, vypnuto = nebytový. Nájem bytu je "
            "podle §56a vždy osvobozený od DPH a nelze ho zdanit ani "
            "nájemci, který je plátce - na rozdíl od nebytových prostor."
        ),
    )

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
    signed_on = models.DateField(
        "Datum podpisu", null=True, blank=True,
        help_text="Tiskne se na Kartu nájemce (Příloha č. 1). Pokud není vyplněno, předvyplní se při uložení podle Platnost od.",
    )
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
        parts = [str(self.client)]
        if self.unit:
            parts.append(str(self.unit))
        if self.valid_from:
            parts.append(f"od {self.valid_from:%-m/%Y}")
        return " – ".join(parts)

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
        if not self.signed_on and self.valid_from:
            self.signed_on = self.valid_from
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

    def rent_for_period(self, period):
        """Najem karty za dane obdobi, zkraceny podle poctu aktivnich dni.

        Soucet CardUnit.monthly_rent (plocha x sazba / 12) vynasobeny
        pomerem aktivnich dni karty k delce obdobi - kdyz platnost zacne
        nebo skonci uprostred mesice, plati klient jen pomernou cast,
        stejne jako u pausalu a vazenych podilu ve vyuctovani sluzeb
        (viz billing/engine.py _kraceno_dny). Karta platna cely mesic
        vraci presne to, co drive, takze se dosavadni cisla nemeni.

        Zaokrouhluje se NAHORU na cele koruny (ROUND_CEILING) - tak se
        najemne skutecne fakturuje, viz report Prehled najemneho.
        Viz konverzace s Danielem 2026-08-17."""
        from decimal import ROUND_CEILING

        raw = sum(
            (cu.monthly_rent or Decimal("0") for cu in self.card_units.all()),
            Decimal("0"),
        )
        if not raw:
            return Decimal("0")
        period_start, period_end = period.date_range()
        active_days = self.active_days_in_period(period_start, period_end)
        if active_days <= 0:
            return Decimal("0")
        dnu = period.days_in_period
        if active_days < dnu:
            raw = raw * Decimal(active_days) / Decimal(dnu)
        return raw.quantize(Decimal("1"), rounding=ROUND_CEILING)

    def rent_not_invoiced_for_period(self, period):
        """Nefakturovana cast najmu za obdobi, krácená stejne jako
        rent_for_period - je to soucast najmu, takze u karty platne jen
        cast mesice se krati se zbytkem.

        Scita se z jednotlivych Ploch karty (CardUnit.rent_not_invoiced) -
        najemne neni Trida a nema Klice, takze i tahle odchylka patri
        primo k Plose, ne na Kartu. Viz konverzace s Danielem 2026-08-19
        (klient plati cast najmu bez dokladu)."""
        from decimal import ROUND_CEILING

        raw = sum(
            (cu.rent_not_invoiced or Decimal("0") for cu in self.card_units.all()),
            Decimal("0"),
        )
        if not raw:
            return Decimal("0")
        period_start, period_end = period.date_range()
        active_days = self.active_days_in_period(period_start, period_end)
        if active_days <= 0:
            return Decimal("0")
        dnu = period.days_in_period
        if active_days < dnu:
            raw = raw * Decimal(active_days) / Decimal(dnu)
        return raw.quantize(Decimal("1"), rounding=ROUND_CEILING)

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
    is_current = models.BooleanField(
        "Aktuální období", default=False,
        help_text=(
            "Období, se kterým se právě pracuje - předvyplní se ve všech "
            "sestavách. Není to totéž co kalendářní měsíc: v srpnu se běžně "
            "rozúčtovává červenec. Aktuální může být vždy jen jedno období, "
            "zaškrtnutím se ostatní automaticky odznačí."
        ),
    )
    vat_rate = models.DecimalField(
        "Sazba DPH (%)", max_digits=5, decimal_places=2, default=Decimal("21"),
        help_text=(
            "Základní sazba DPH platná v tomto období - používá se ve sloupcích "
            "„vč. DPH\" v Přehledu nájemného. Je u období, aby změna sazby "
            "neovlivnila zpětně už uzavřená období."
        ),
    )

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

    def save(self, *args, **kwargs):
        """Aktuální období může být jen jedno - zaškrtnutí odznačí ostatní."""
        super().save(*args, **kwargs)
        if self.is_current:
            Period.objects.exclude(pk=self.pk).filter(is_current=True).update(is_current=False)

    @classmethod
    def current(cls):
        """Období, které se má v sestavách předvyplnit.

        Primárně to, které je ručně označené jako Aktuální (is_current) -
        pracovní období totiž není totéž co kalendářní měsíc: v srpnu se
        běžně rozúčtovává červenec, takže si ho Daniel nastavuje sám
        (viz konverzace 2026-08-15).

        Když žádné označené není, spadne se na kalendářní odhad: období
        dnešního měsíce, jinak nejnovější už začaté (ne budoucí), a kdyby
        v DB byla jen budoucí, tak nejbližší z nich. Ten fallback tu je
        proto, že dřív se všude používalo `Period.objects.first()`
        (= nejnovější podle Meta.ordering) a od zavedení tlačítka
        "Generovat pro celý rok" jsou v DB i budoucí měsíce, takže
        sestavy najížděly třeba na prosinec. Vrací None jen když není
        žádné období.
        """
        marked = cls.objects.filter(is_current=True).first()
        if marked is not None:
            return marked
        today = date.today()
        exact = cls.objects.filter(year=today.year, month=today.month).first()
        if exact is not None:
            return exact
        started = cls.objects.filter(
            models.Q(year__lt=today.year)
            | models.Q(year=today.year, month__lt=today.month)
        ).first()
        if started is not None:
            return started
        return cls.objects.order_by("year", "month").first()


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
    # Drzi KOD Tridy (InvoiceClassColor.invoice_class). Nazev pole
    # zustava "meter_type" kvuli zpetne kompatibilite dat a starsich
    # prikazu - prejmenovani sloupce by znamenalo migraci a upravu
    # desitek mist bez uzitku.
    meter_type = models.CharField("Třída", max_length=20)
    unit_of_measure = models.CharField(
        "Měrná jednotka", max_length=20, blank=True, default="",
        help_text=(
            "Nech prázdné a doplní se výchozí jednotka Třídy (Nastavení → Třídy). "
            "Dřív tu byla natvrdo „kWh“, takže vodoměr nebo teploměr založený bez "
            "vyplnění jednotky dostal kWh."
        ),
    )
    reading_unit_of_measure = models.CharField(
        "Jednotka odečtu (na displeji)", max_length=20, blank=True,
        help_text=(
            "Jednotka, ve které se odečet fyzicky čte z měřidla - zobrazí se "
            "na stránce Zadávání odečtů. Vyplň jen když se liší od Měrné "
            "jednotky, tedy když je Koeficient jiný než 1 (např. teplo se "
            "čte v kWh, ale vykazuje v GJ). Prázdné = stejná jako Měrná jednotka."
        ),
    )
    coefficient = models.DecimalField(
        "Koeficient (odečet × koef. = spotřeba)", max_digits=12, decimal_places=6, default=Decimal("1"),
        help_text=(
            "Násobitel odečtu pro převod na měrnou jednotku měřidla. Např. teplo "
            "měřené v kWh, ale vykazované v GJ: koeficient = 0,0036 "
            "(1 GJ = 277,778 kWh). Výchozí 1 = beze změny. Poměry mezi kartami "
            "(a tím rozúčtované Kč) se nemění, mění se jen jednotky/čísla."
        ),
    )
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
    supply_point = models.ForeignKey(
        "SupplyPoint", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="member_meters", verbose_name="Odběrné místo",
        help_text=(
            "Pod které odběrné místo (EAN) toto měřidlo fyzicky patří. "
            "Slouží k reconciliaci 'dodáno vs. naměřeno' v přehledu spotřeb. "
            "Nech prázdné u přívodního/fakturačního měřidla samotného odběru "
            "(např. 668_CELKEM) - to se nastavuje na Odběrném místě jako "
            "'Přívodní měřidlo', ne jako jeho vlastní člen."
        ),
    )

    class Meta:
        verbose_name = "Měřidlo"
        verbose_name_plural = "Měřidla"
        ordering = ["site", "meter_type", "code"]

    def __str__(self):
        return self.code or self.name

    def save(self, *args, **kwargs):
        """Prazdna Merna jednotka se doplni podle Tridy.

        Pole drive melo natvrdo default="kWh", takze vodomer i teplomer
        zalozeny bez vyplneni jednotky dostal kWh - presne tak vznikl
        W_FM_CELKEM s jednotkou kWh misto m³. Ted se bere vychozi
        jednotka Tridy (InvoiceClassColor.default_unit_of_measure), a to
        i mimo admin (importy, shell). Kdyz Trida vychozi jednotku nema,
        zustane prazdna. Viz konverzace s Danielem 2026-08-19."""
        if not self.unit_of_measure and self.meter_type:
            vychozi = InvoiceClassColor.default_unit_map().get(self.meter_type)
            if vychozi:
                self.unit_of_measure = vychozi
        super().save(*args, **kwargs)

    @property
    def jednotka_odectu(self):
        """Jednotka, kterou spravce vidi u policka pro odecet.

        Odecet se zadava v jednotce z DISPLEJE meridla, kdezto
        `unit_of_measure` je jednotka az PO prepoctu koeficientem
        (u tepla se cte kWh, ale vykazuje GJ pri koef. 0,0036). Na
        strance odectu se proto ukazuje tahle, ne `unit_of_measure` -
        driv tam u vsech meridel tepla svitilo GJ, i kdyz se do nich
        zadavaly kWh. Viz konverzace s Danielem 2026-08-19."""
        return self.reading_unit_of_measure or self.unit_of_measure

    def get_meter_type_display(self):
        """Django tuhle metodu generuje samo jen u poli s choices= - to uz
        pole nema (zivy seznam Trid je v InvoiceClassColor), takze ji
        dodavame rucne, stejne jako u ServicePoolItem.
        get_invoice_class_display. Bez ni padala stranka odectu
        (meters/views.py) i sestava Neprirazena meridla na
        AttributeError - viz konverzace s Danielem 2026-08-19."""
        return InvoiceClassColor.label_map().get(self.meter_type, self.meter_type)

    def consumption_for(self, period, readings_cache=None):
        """`readings_cache`: volitelny dict {(meter_id, period_id):
        MeterReading} pro hromadne predem nactene odecty (viz
        billing/engine.py calculate_period) - misto dvou samostatnych
        DB dotazu (aktualni + predchozi obdobi) na KAZDE meridlo se
        pouzije uz nacteny objekt z pameti. Bez cache (vychozi, vsechny
        ostatni volajici - admin, reporty, diagnosticke prikazy) se
        chova uplne stejne jako drive.

        Vysledek REALNEHO meridla se nasobi polem `coefficient` (prevod
        odectu na merenou jednotku, napr. teplo kWh -> GJ koeficient 0,0036).
        U virtualniho meridla se koeficient neuplatnuje - jeho slozky uz
        maji svuj koeficient zapocitany. Pomery mezi meridly se koeficientem
        (stejnym pro celou tridu) nemeni, takze rozuctovane Kc zustavaji."""
        if self.is_virtual:
            return self._formula_consumption_for(period, readings_cache=readings_cache)
        raw = self._raw_meter_consumption(period, readings_cache=readings_cache)
        if raw is None:
            return None
        return raw * (self.coefficient if self.coefficient is not None else Decimal("1"))

    def _raw_meter_consumption(self, period, readings_cache=None):
        """Surova spotreba realneho meridla z odectu, JESTE bez koeficientu -
        bud primo zadana Spotreba (reading_mode CONSUMPTION), nebo rozdil
        stavu (vc. vymeny meridla pres reset_from_value). Viz consumption_for."""
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
        spotrebu jinych mericí stejneho arealu podle jejich kodu.

        DULEZITE: kazdy clen vzorce vstupuje svou VLASTNI spotrebou
        (surovy odecet minus jeho prime samostatne merene podprostory),
        NE surovym odectem - viz _consumption_net_of_children. U meridla
        bez deti je to totez co surovy odecet (napr. 668NT/668VT), takze
        proste vzorce se chovaji beze zmeny. U master meridla to ale
        zabrani dvojimu zapocteni: E_SPOL = E_A7+E_A8+E_A9+D_VS, kde E_A7
        je master pro E_A1..E_A6 (samostatne uctovane najemniky) - do
        spolecne spotreby ma vstoupit jen zbytek E_A7 (~473), ne cely
        surovy odecet vc. najemniku (1214). Viz konverzace s Danielem
        2026-08-13 a stejny princip v core/admin.py report_spotreby_view."""
        total = None
        for meter, sign in self._formula_tokens():
            value = meter._consumption_net_of_children(period, readings_cache=readings_cache)
            if value is None:
                continue
            signed_value = sign * value
            total = signed_value if total is None else total + signed_value
        return total

    def _consumption_net_of_children(self, period, readings_cache=None):
        """Spotreba meridla ocistena o jeho prime podruzne meridla - pro
        pouziti jako clen ve Vzorci virtualniho meridla (napr. E_SPOL).
        Surovy odecet minus SUROVA spotreba primych deti (Meter.children).

        Odecita se SUROVA spotreba primeho ditete (child.consumption_for),
        NE jeho uz zredukovana vlastni hodnota - u vicevrstve hierarchie
        (A7 -> A4 -> A4KLIMA) to spravne teleskopuje k tomu, ze soucet
        vsech vlastnich hodnot v podstromu == surovy odecet korene, takze
        se zadna spotreba nezapocita dvakrat ani nevytrati. Stejna logika
        jako owned_consumption v core/admin.py report_spotreby_view a
        _owned_consumption v billing/engine.py (tam se ale odecitaji jen
        deti fakturovane na TEZE polozce; tady, uvnitr vzorce, se odecitaji
        vsechny prime deti - shodne s reportem, ktery ma overit fyzicky
        strom). Viz konverzace s Danielem 2026-08-13.

        Virtualni clen pocita svou spotrebu uz ze sveho vlastniho Vzorce
        (ktery si sve deti resi sam) - fyzickou master/podruzne hierarchii
        maji jen realna meridla, takze u nej se nic neodecita."""
        if self.is_virtual:
            return self._formula_consumption_for(period, readings_cache=readings_cache)
        raw = self.consumption_for(period, readings_cache=readings_cache)
        if raw is None:
            return None
        deduction = Decimal("0")
        for child in self.children.all():
            child_consumption = child.consumption_for(period, readings_cache=readings_cache)
            if child_consumption is not None:
                deduction += child_consumption
        # Spotreba nikdy nesmi jit do zaporu - kdyz podruzna meridla
        # namerila vic nez nadrazene (proměření, ruzne dny odectu, vadne
        # meridlo), orizne se na nulu. Rozdil se rozpusti do celku:
        # rozdeluje se NAKLAD v Kc, ne kWh, takze celkova castka zustava
        # a ostatnim se jen nepatrne zmeni podil. Viz konverzace
        # s Danielem 2026-08-17 (E_D1 18 kWh vs bojler 22 kWh).
        return max(raw - deduction, Decimal("0"))

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


class SupplyPoint(models.Model):
    """Odberne misto / EAN - fyzicky pripojny bod dodavky energie (napr.
    "EAN 668" nebo "Hlavni odber elektro FM"). Pod jedno odberne misto
    spada vic podruznych meridel (Meter.supply_point / related_name
    member_meters). "Privod" (main_meter) je meridlo, jehoz spotreba =
    kolik do odberneho mista celkem doslo od dodavatele (napr. virtualni
    668_CELKEM = 668NT+668VT); muze zustat prazdny, kdyz se dodane
    mnozstvi bere jen z faktury a zadne hlavni meridlo neexistuje (napr.
    "Hlavni odber elektro FM"). Slouzi k reconciliaci v prehledu spotreb:
    dodano (main_meter) vs. soucet vlastnich spotreb clenskych meridel =
    ztraty/nezmereno. Viz konverzace s Danielem 2026-08-12."""
    site = models.ForeignKey(
        Site, on_delete=models.CASCADE, related_name="supply_points", verbose_name="Areál"
    )
    name = models.CharField(
        "Název", max_length=200,
        help_text="Např. 'EAN 668' nebo 'Hlavní odběr elektro FM'.",
    )
    code = models.CharField("Kód / EAN", max_length=50, blank=True)
    # Stejne jako u Meter.meter_type - drzi KOD Tridy. Vychozi hodnota je
    # napsana primo, protoze ServicePoolItem.InvoiceClass je definovana az
    # nize v souboru (nelze na ni tady odkazat).
    meter_type = models.CharField(
        "Třída", max_length=20, default="elektro",
    )
    main_meter = models.ForeignKey(
        Meter, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="supplies_as_main", verbose_name="Přívodní měřidlo (dodaná spotřeba)",
        help_text=(
            "Měřidlo, jehož spotřeba = kolik do odběrného místa celkem "
            "došlo od dodavatele (např. 668_CELKEM). Nech prázdné, pokud "
            "se dodané množství bere jen z faktury a žádné hlavní měřidlo "
            "neexistuje."
        ),
    )
    legal_loss_pct = models.DecimalField(
        "Zákonná ztráta %", max_digits=5, decimal_places=2, default=Decimal("0"),
        help_text=(
            "Zákonná (systémová) ztráta, kterou dodavatel účtuje navíc - "
            "typicky 4 % u velkoodběru. Faktura už ztrátu obsahuje "
            "(dodavatel k reálně dodanému připočítá tato %), takže reálně "
            "dodané = faktura / (1 + %/100); do vyúčtování se klientům ztráta "
            "vrací. Co zůstane po odečtení této i naměřené spotřeby jsou "
            "skutečné ztráty (proměření / pozdní odečet). 0 = nepoužít "
            "(např. EAN 668, kde čteme vlastní měřidla)."
        ),
    )
    cost_item = models.ForeignKey(
        "ServicePoolItem", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="supplies_as_cost_source", verbose_name="Náklad, ze kterého brát fakturované množství",
        help_text=(
            "Položka zásobníku, jejíž Fakturované množství se má přepisovat "
            "do Přívodního měřidla (akce „Dotáhnout fakturovaná množství“ "
            "u Období). Nastav jen u odběrů, kde se dodané množství bere "
            "z faktury, ne z vlastního měřidla - jinak nech prázdné. "
            "Hádat to podle areálu a třídy nejde: teplo NJ má dvě položky "
            "(pelety a záložní elektrokotel) a u vody by se do toho připletly "
            "srážkové vody, které v jednotkách nesou m² plochy, ne m³."
        ),
    )
    note = models.CharField("Poznámka", max_length=300, blank=True)

    class Meta:
        verbose_name = "Odběrné místo"
        verbose_name_plural = "Odběrná místa"
        ordering = ["site", "meter_type", "name"]

    def __str__(self):
        return self.name

    def get_meter_type_display(self):
        """Stejny duvod jako u Meter.get_meter_type_display - pole uz nema
        choices=. Zatim to nikdo nevola, ale je to stejna mina: u Meter
        prave takove volani shodilo stranku odectu."""
        return InvoiceClassColor.label_map().get(self.meter_type, self.meter_type)


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
        """Ponecháno jako zdroj výchozí hodnoty pole a kvůli starším
        jednorázovým příkazům - živý seznam Tříd je v InvoiceClassColor
        (Nastavení -> Třídy), takže tenhle výčet už neurčuje povolené
        volby ani popisky."""
        ELECTRICITY = "elektro", "Elektřina"
        WATER = "voda", "Voda"
        HEAT = "teplo", "Teplo"
        OTHER = "ostatni", "Ostatní"

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
        "Třída", max_length=20, default=InvoiceClass.OTHER
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
        verbose_name = "Položka zásobníku služeb"
        verbose_name_plural = "Zásobník služeb"
        ordering = ["site", "invoice_class", "name"]

    def __str__(self):
        return f"{self.name} ({self.site})"

    def get_invoice_class_display(self):
        """Django tuhle metodu generuje samo jen u poli s choices= - to uz
        pole nema (zivy seznam Trid je v InvoiceClassColor), takze ji
        dodavame rucne, aby vsechna volani dal fungovala a zaroven
        respektovala prejmenovani Tridy v adminu."""
        return InvoiceClassColor.label_map().get(self.invoice_class, self.invoice_class)


class InvoiceClassColor(models.Model):
    """Trida (Elektrina/Voda/Teplo/Ostatni/Najemne) - JEDINY seznam, do
    ktereho se radi jak polozky zasobniku sluzeb, tak Meridla a Odberna
    mista. Drive byly dva nezavisle vycty: Meter.MeterType (Typ meridla, uz zrusen)
    a ServicePoolItem.InvoiceClass (Trida) - vznikly v jine dobe pro jiny
    ucel a nikdy se nesjednotily, i kdyz slo temer o totez (lisil se jen
    "Plyn" bez vlastni tridy a "Nájemné" bez meridel). Daniel na tu
    duplicitu upozornil 2026-08-18 a Typy meridel jsme zrusili uplne -
    meridlo si vybira primo Tridu.

    Radky jdou v adminu pridavat, prejmenovat i mazat (viz
    core/admin.py InvoiceClassColorAdmin). Kod (invoice_class) je jen
    interni odkaz - Polozky/Meridla/Odberna mista na nej odkazuji
    obycejnym textem (neni to FK), proto se po zalozeni needituje."""
    invoice_class = models.CharField(
        "Kód", max_length=20, unique=True,
        help_text="Interní kód - odkazují na něj Položky, Měřidla i Odběrná místa. Needitovatelný po založení.",
    )
    label = models.CharField(
        "Název", max_length=50, blank=True,
        help_text="Jak se Třída zobrazuje v adminu. Prázdné = použije se Kód.",
    )
    default_unit_of_measure = models.CharField(
        "Výchozí měrná jednotka", max_length=20, blank=True,
        help_text="Např. kWh, m³, GJ. Použije se v přehledu spotřeb u měřidel bez vlastní jednotky.",
    )
    sort_order = models.PositiveIntegerField(
        "Pořadí", default=0,
        help_text="Určuje pořadí Tříd v sestavách a nabídkách.",
    )
    color_light = models.CharField(
        "Barva pozadí (světlý motiv)", max_length=7, default="#f3f4f6",
        help_text="Formát #rrggbb.",
    )
    color_dark = models.CharField(
        "Barva pozadí (tmavý motiv)", max_length=7, default="#1f2937",
        help_text="Formát #rrggbb.",
    )
    # Barva TEXTU se pouziva v seznamech, kde by cele barevne pozadi radku
    # bylo prilis (Měřidla, Odběrná místa, Odečty, Ceníky, Náklady) -
    # obarvi se jen kod/nazev. Dve varianty, protoze jeden odstin necte
    # dobre v obou motivech: na bilem pozadi je potreba tmavsi, na tmavem
    # svetlejsi. Viz konverzace s Danielem 2026-08-16.
    text_color_light = models.CharField(
        "Barva textu (světlý motiv)", max_length=7, default="#374151",
        help_text="Formát #rrggbb. Použije se v seznamech Měřidla, Odečty, Ceníky…",
    )
    text_color_dark = models.CharField(
        "Barva textu (tmavý motiv)", max_length=7, default="#d1d5db",
        help_text="Formát #rrggbb.",
    )
    deduct_fixed_from_pool = models.BooleanField(
        "Odečítat paušály z celkového nákladu", default=True,
        help_text=(
            "Zapnuto: paušály (Pevná částka / Dle výměry) se nejdřív odečtou "
            "z nákladu a mezi ostatní se dělí jen zbytek - klienti s měřidlem "
            "tak platí méně. Vypnuto: paušály jdou navíc a celý náklad se dělí "
            "mezi ostatní, jako to dělal starý systém. Platí pro celou třídu; "
            "jednotlivý klíč může odečítání vypnout i tak, zapnout ale ne."
        ),
    )
    ma_sekci_klicu = models.BooleanField(
        "Vlastní sekce v Kartě klienta a na Ploše", default=True,
        help_text=(
            "Zapnuto: Třída má v Kartě klienta vlastní sekci Klíčů a na Ploše "
            "sekci Výchozích služeb. Vypni u Tříd, které se nerozúčtovávají "
            "klíči - typicky Nájemné, to se zadává v sekci Plochy a nájemné."
        ),
    )

    class Meta:
        verbose_name = "Třída"
        verbose_name_plural = "Třídy"
        ordering = ["sort_order", "invoice_class"]

    @classmethod
    def deduct_fixed_map(cls):
        """{invoice_class: bool} - jestli se u te tridy maji pausaly odecitat
        z celkoveho nakladu. Trida, ktera v tabulce neni, se chova jako
        zapnuta (puvodni chovani). Viz konverzace s Danielem 2026-08-16."""
        return dict(cls.objects.values_list("invoice_class", "deduct_fixed_from_pool"))

    @classmethod
    def choices(cls):
        """[(kod, nazev)] ve zvolenem poradi - nahrazuje drive napevno
        zapsany ServicePoolItem.InvoiceClass.choices vsude, kde se staví
        nabidky a skupiny sestav."""
        return [
            (code, label or code)
            for code, label in cls.objects.values_list("invoice_class", "label")
        ]

    @classmethod
    def se_sekci(cls):
        """Tridy, ktere maji mit vlastni inline sekci - z nich se generuji
        sekce Klicu v Karte klienta a Vychozich sluzeb na Plose (viz
        core/admin.py sekce_klicu/sekce_sluzeb). Poradi je dane Meta.ordering,
        aby bylo deterministicke."""
        return list(cls.objects.filter(ma_sekci_klicu=True))

    @classmethod
    def label_map(cls):
        """{kod: nazev} - pro zobrazeni Tridy tam, kde je po ruce jen kod."""
        return {code: (label or code) for code, label in cls.objects.values_list("invoice_class", "label")}

    @classmethod
    def default_unit_map(cls):
        """{kod: vychozi jednotka} - fallback jednotky v prehledu spotreb."""
        return dict(
            cls.objects.exclude(default_unit_of_measure="")
            .values_list("invoice_class", "default_unit_of_measure")
        )

    @classmethod
    def css_class_for(cls, invoice_class):
        """Nazev CSS tridy, kterou generuje core.views.class_colors_css."""
        return f"rx-class-{invoice_class}" if invoice_class else ""

    @classmethod
    def css_class_for_meter_type(cls, meter_type):
        """Meridlo uz drzi primo kod Tridy (drive samostatny Typ meridla,
        ktery se na Tridu teprve mapoval) - zustava jako tenka obalka,
        aby se nemusela prepisovat vsechna volani v adminu."""
        return cls.css_class_for(meter_type)

    def __str__(self):
        return self.label or self.invoice_class


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
    unit_price = models.DecimalField(
        "Cena za m²/rok (přebíjí Ceník)", max_digits=12, decimal_places=4, null=True, blank=True,
        help_text=(
            "Jen pro typ 'Dle výměry (m²)'. Dohodnutá cena Kč/m²/rok pro TUTO "
            "kartu - přebíjí cenu z Ceníku položky (např. individuálně sjednaný "
            "paušál). Nech prázdné, aby se použila cena z Ceníku (implicitní "
            "default). Měsíční částka = Hodnota (m²) × tato cena / 12."
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

    _tracked_fields = ("period_id", "price_per_unit", "note")

    def clean(self):
        if self.period_id and self.period.status == Period.Status.CLOSED and self._price_data_changed():
            raise ValidationError("Období je uzavřené, ceník nejde přidat ani upravit.")

    def _price_data_changed(self):
        """Viz CostEntry._cost_data_changed - povoli ulozit nezmeneny radek
        v uzavrenem obdobi, jen skutecnou zmenu zablokuje."""
        if not self.pk:
            return True
        original = PriceList.objects.filter(pk=self.pk).values(*self._tracked_fields).first()
        if original is None:
            return True
        return any(original[field] != getattr(self, field) for field in self._tracked_fields)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

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
    supplier = models.CharField(
        "Dodavatel / zdroj", max_length=100, blank=True,
        help_text=(
            "Vyplň jen když má položka za období VÍC faktur od různých "
            "dodavatelů (např. elektřina FM: TEDOM EAN 240 + SZYPKA EAN, "
            "nebo teplo NJ: pelety + záložní elektrokotel). Náklady se "
            "sečtou a rozúčtují jako jeden celek."
        ),
    )
    price_per_unit = models.DecimalField(
        "Cena za jednotku (Kč)", max_digits=12, decimal_places=4,
        null=True, blank=True,
        help_text=(
            "Přebíjí Ceník. Vyplň, když má tenhle dodavatel jinou cenu než "
            "ostatní - jinak nech prázdné a cena se vezme z Ceníku."
        ),
    )
    unit_of_measure = models.CharField(
        "Jednotka", max_length=20, blank=True,
        help_text=(
            "kWh, m³, GJ, kg… Použije se jen k rozlišení, jestli jdou "
            "množství z více faktur sečíst. Když se jednotky liší (pelety "
            "v kg vs elektrokotel v kWh), rozúčtuje se pouze v Kč a "
            "množství se nikde neukazuje."
        ),
    )
    note = models.CharField("Poznámka", max_length=300, blank=True)

    class Meta:
        verbose_name = "Náklad za období"
        verbose_name_plural = "Náklady za období"
        ordering = ["-period", "service_item"]

    def __str__(self):
        popis = f" ({self.supplier})" if self.supplier else ""
        if self.amount_units is not None:
            return f"{self.service_item} – {self.period}{popis}: {self.amount_units} j"
        return f"{self.service_item} – {self.period}{popis}: {self.amount_czk} Kč"

    @classmethod
    def totals_for(cls, service_item, period, price_cache=None, entries=None):
        """Souhrn VSECH nakladu polozky za obdobi - jedno misto pravdy pro
        engine, sestavy i kontroly.

        Polozka muze mit vic faktur od ruznych dodavatelu (elektrina FM =
        TEDOM + SZYPKA, teplo NJ = pelety + zalozni elektrokotel). Rozuctuje
        se jejich SOUCET jako jeden celek - fyzicky jde o jednu dodavku do
        stejne site, jen fakturovanou nadvakrat.

        Vraci dict:
          czk    - soucet castek (None, kdyz zadnou nelze urcit)
          units  - soucet mnozstvi, ale JEN kdyz maji vsechny faktury
                   stejnou jednotku; pri ruznych jednotkach None, protoze
                   kg pelet a kWh elektriny secist nejde (Daniel 2026-08-16:
                   "budeme resit pouze rozuctovani v Kc, nebudeme ukazovat
                   primo jednotky")
          unit   - ta spolecna jednotka, nebo ""
          count  - kolik faktur se seclo

        `entries`: uz nactene naklady (aby se nedotazovalo znovu v cyklu).
        """
        if entries is None:
            entries = list(cls.objects.filter(service_item=service_item, period=period))
        if not entries:
            return {"czk": None, "units": None, "unit": "", "count": 0}

        czk = None
        for ce in entries:
            castka = ce.get_amount_czk(period, price_cache=price_cache)
            if castka is not None:
                czk = (czk or Decimal("0")) + castka

        jednotky = {(ce.unit_of_measure or "").strip() for ce in entries}
        units = None
        if len(jednotky) == 1 and all(ce.amount_units is not None for ce in entries):
            units = sum((ce.amount_units for ce in entries), Decimal("0"))
        return {
            "czk": czk, "units": units,
            "unit": jednotky.pop() if len(jednotky) == 1 else "",
            "count": len(entries),
        }

    _tracked_fields = ("period_id", "amount_units", "amount_czk", "note")

    def clean(self):
        """0 v amount_units/amount_czk NENÍ totéž co prázdné pole -
        get_amount_czk() bere `is not None`, takže amount_czk=0 by se
        vzalo jako skutečná (a konečná) nulová částka a amount_units by
        se vůbec nepoužilo - položka by se klientům potichu vyúčtovala
        na 0 Kč. Kdo nemá pro tenhle záznam částku/množství, ať pole
        nechá prázdné, ne 0 (viz konverzace s Danielem)."""
        if self.period_id and self.period.status == Period.Status.CLOSED and self._cost_data_changed():
            raise ValidationError("Období je uzavřené, náklad nejde přidat ani upravit.")
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

    def _cost_data_changed(self):
        """True pro novy naklad nebo pokud se u existujiciho zmenil nektery
        ze sledovanych udaju (obdobi/mnozstvi/castka/poznamka). Diky tomu
        jde v uzavrenem obdobi ulozit nezmeneny zaznam (napr. hromadny save
        v adminu), jen skutecna zmena se zablokuje - stejny princip jako
        MeterReading._reading_data_changed."""
        if not self.pk:
            return True
        original = CostEntry.objects.filter(pk=self.pk).values(*self._tracked_fields).first()
        if original is None:
            return True
        return any(original[field] != getattr(self, field) for field in self._tracked_fields)

    def save(self, *args, **kwargs):
        """Jakmile se doplni amount_units nebo amount_czk, sama zmizi
        znacka NOTE_K_DOPLNENI (viz core/admin.py
        PeriodAdmin.vygenerovat_chybejici_naklady) - jinak by v Poznamce
        zustavala navzdy, i kdyz uz zaznam neni "k doplneni", a matla by
        pozdejsi hledani/filtr Stav=Nevyplneno."""
        self.clean()
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
            # Cena primo na nakladu ma prednost pred Cenikem - dodavatele
            # jedne polozky mivaji ruzne ceny (elektrina FM: TEDOM vs
            # SZYPKA), takze jedna cena v Ceniku by nestacila.
            if self.price_per_unit is not None:
                return self.amount_units * self.price_per_unit
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
    rent_not_invoiced = models.DecimalField(
        "Nefakturovaná část (Kč/měsíc)",
        max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text=(
            "Část měsíčního nájmu za tuto plochu, kterou klient platí bez "
            "dokladu - do nájmu a sestav se počítá dál, ale NEfakturuje se "
            "a nevstupuje do koeficientu DPH (není zdanitelné plnění). "
            "Nech 0, pokud se fakturuje celý nájem."
        ),
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
