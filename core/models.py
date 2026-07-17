"""
Zakladni entity: arealy/objekty, pronajimane prostory, klienti
a jejich karty (najemni vztahy s platnosti).
"""
import calendar
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models


# Typy rozpoctu - sdileno mezi ServicePoolItem (vychozi typ) a AllocationKey
# (skutecny typ pouzity na konkretni karte klienta).
ALLOCATION_TYPE_CHOICES = [
    ("percent", "Procento"),
    ("area_ratio", "Podle výměry (m²)"),
    ("person_count", "Podle počtu osob"),
    ("equal_split", "Rovným dílem"),
    ("submeter", "Podružné měřidlo (1:1)"),
    ("fixed_amount", "Pevná částka"),
    ("weighted_count", "Podle váhy (počet jednotek)"),
]


class Site(models.Model):
    """Areal nebo objekt (prumyslovy areal, bytovy dum...)."""

    name = models.CharField("Nazev", max_length=200)
    address = models.CharField("Adresa", max_length=300, blank=True)

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
    code = models.CharField("Kód / označení", max_length=50, blank=True)
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

    bank_name = models.CharField("Banka", max_length=50, blank=True)
    bank_account = models.CharField("Číslo účtu", max_length=50, blank=True)
    bank_code = models.CharField("Kód banky", max_length=10, blank=True)

    contact_email = models.EmailField("E-mail", blank=True)
    contact_phone = models.CharField("Telefon", max_length=50, blank=True)
    note = models.CharField("Poznámka", max_length=500, blank=True)

    class Meta:
        verbose_name = "Klient"
        verbose_name_plural = "Klienti"
        ordering = ["name"]

    def __str__(self):
        return self.name


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

    class Meta:
        verbose_name = "Karta klienta"
        verbose_name_plural = "Karty klientů"
        ordering = ["client", "valid_from"]

    def __str__(self):
        return self.description or f"Karta {self.client}"

    def clean(self):
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError("Datum 'platnost do' nesmí být dříve než 'platnost od'.")
        if self.is_active:
            qs = ClientCard.objects.filter(client=self.client, is_active=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    f"Klient {self.client} již má aktivní kartu: {qs.first().description}. "
                    "Nejprve deaktivujte stávající kartu."
                )

    def active_days_in_period(self, period_start, period_end):
        start = max(self.valid_from, period_start)
        end = min(self.valid_to or period_end, period_end)
        if end < start:
            return 0
        return (end - start).days + 1


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
        help_text="Kratky kod pro odkazovani ve vzorcich virtualnich mericu (napr. E_A1).",
    )
    name = models.CharField("Název / označení", max_length=200)
    meter_type = models.CharField("Typ", max_length=20, choices=MeterType.choices)
    unit_of_measure = models.CharField("Měrná jednotka", max_length=20, default="kWh")
    reading_mode = models.CharField(
        "Způsob zadávání odečtů", max_length=20, choices=ReadingMode.choices, default=ReadingMode.STATE,
        help_text=(
            "Vetsina meridel hlasi kumulativni Stav (spotreba se dopocita jako "
            "rozdil vuci minulemu obdobi). Pokud dodavatel hlasi rovnou Spotrebu "
            "za obdobi (napr. hlavni odberne misto elektro), prepni na tento rezim "
            "- pak staci zadat odecet jen za aktualni obdobi, hodnota se pouzije primo."
        ),
    )
    serial_number = models.CharField("Výrobní číslo", max_length=100, blank=True)
    is_virtual = models.BooleanField(
        "Virtuální (vypočtené)", default=False,
        help_text="Spotreba se nepocita z odectu, ale ze vzorce odkazujiciho na jine mericí (pole Vzorec).",
    )
    formula = models.CharField(
        "Vzorec", max_length=300, blank=True,
        help_text="Pouze pro virtualni mericí, napr. E_A1+E_AB1 (kody jinych mericí).",
    )

    class Meta:
        verbose_name = "Měřidlo"
        verbose_name_plural = "Měřidla"
        ordering = ["site", "meter_type", "code"]

    def __str__(self):
        return self.code or self.name

    def consumption_for(self, period):
        current = self.readings.filter(period=period).first()
        if current is None:
            return None

        if self.reading_mode == self.ReadingMode.CONSUMPTION:
            # Dodavatel hlasi rovnou spotrebu za obdobi - zadana hodnota
            # se pouzije primo, neni potreba znat predchozi obdobi.
            return current.value

        prev_period = period.previous_period()
        if prev_period is None:
            return None
        previous = self.readings.filter(period=prev_period).first()
        if previous is None:
            return None
        return current.value - previous.value


class MeterReading(models.Model):
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name="readings", verbose_name="Měřidlo")
    period = models.ForeignKey(Period, on_delete=models.CASCADE, related_name="readings", verbose_name="Období")
    reading_date = models.DateField("Datum odečtu")
    value = models.DecimalField(
        "Stav / spotřeba", max_digits=14, decimal_places=3,
        help_text="Podle nastaveni mericí: bud kumulativni stav, nebo rovnou spotreba za obdobi.",
    )
    is_estimate = models.BooleanField("Odhad", default=False)
    note = models.CharField("Poznámka", max_length=300, blank=True)

    class Meta:
        verbose_name = "Odečet měřidla"
        verbose_name_plural = "Odečty měřidel"
        unique_together = ("meter", "period")
        ordering = ["-period", "meter"]

    def __str__(self):
        return f"{self.meter} – {self.period}: {self.value}"


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
        help_text="Predvyplni se pri zalozeni noveho klice na karte klienta pro tuto polozku.",
    )
    default_amount_czk = models.DecimalField(
        "Výchozí měsíční částka (Kč)", max_digits=12, decimal_places=2, null=True, blank=True,
        help_text=(
            "Pouzije se pri vypoctu rozuctovani pro obdobi, pro ktere neni "
            "zadany zadny Naklad za obdobi (CostEntry) - typicky pro sluzby "
            "s neměnnou paušální cenou (ostraha, internet...), aby se nemusela "
            "castka zadavat kazdy mesic rucne. Pokud je pro dane obdobi CostEntry "
            "zadany, ma vzdy prednost pred touto vychozi castkou."
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
        PERCENT = "percent", "Procento"
        AREA_RATIO = "area_ratio", "Podle výměry (m²)"
        PERSON_COUNT = "person_count", "Podle počtu osob"
        EQUAL_SPLIT = "equal_split", "Rovným dílem"
        SUBMETER = "submeter", "Podružné měřidlo (1:1)"
        FIXED_AMOUNT = "fixed_amount", "Pevná částka"
        WEIGHTED_COUNT = "weighted_count", "Podle váhy (počet jednotek)"

    client_card = models.ForeignKey(
        ClientCard, on_delete=models.CASCADE, related_name="allocation_keys", verbose_name="Karta klienta"
    )
    service_item = models.ForeignKey(
        ServicePoolItem, on_delete=models.CASCADE, related_name="allocation_keys", verbose_name="Položka zásobníku"
    )
    allocation_type = models.CharField("Typ rozpočtu", max_length=20, choices=AllocationType.choices)
    value = models.DecimalField("Hodnota", max_digits=12, decimal_places=4, null=True, blank=True)
    meter = models.ForeignKey(
        Meter, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="submeter_keys", verbose_name="Podružné měřidlo"
    )
    valid_from = models.DateField(
        "Platnost od", null=True, blank=True,
        help_text="Volitelne - typicky se platnost resi na urovni cele Karty klienta.",
    )
    valid_to = models.DateField("Platnost do", null=True, blank=True)

    class Meta:
        verbose_name = "Klíč"
        verbose_name_plural = "Klíče"
        ordering = ["service_item", "client_card"]

    def __str__(self):
        return f"{self.client_card} – {self.service_item}"

    def is_valid_for_period(self, period):
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
    def get_price_for_period(cls, service_item, period):
        """
        Vrátí cenu za jednotku pro dané nebo nejbližší předchozí období.
        """
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

    def get_amount_czk(self, period=None):
        """Vrátí částku v Kč - buď přímo, nebo přes ceník."""
        if self.amount_czk is not None:
            return self.amount_czk
        if self.amount_units is not None:
            p = period or self.period
            price = PriceList.get_price_for_period(self.service_item, p)
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

    def create_default_keys(self):
        for unit_service in self.unit.unit_services.all():
            AllocationKey.objects.get_or_create(
                client_card=self.card,
                service_item=unit_service.service_item,
                meter=unit_service.meter,
                defaults={
                    "allocation_type": unit_service.allocation_type,
                    "value": unit_service.value,
                },
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
