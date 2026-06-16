"""
Zasobnik sluzeb a odbernych mist, klice pro rozpocet,
skutecne naklady za obdobi a vysledne vyuctovani.
"""
from django.core.exceptions import ValidationError
from django.db import models

from core.models import ClientCard, Unit
from meters.models import Meter, Period


class ServicePoolItem(models.Model):
    """
    Polozka Zasobniku - sluzba nebo odberne misto vztazene
    k pronajatemu prostoru (napr. "Elektřina - hlavní měřidlo",
    "Úklid společných prostor", "Odvoz odpadu").

    Pokud je vyplneno `meter`, jde o merenou polozku - odecty
    tohoto meridla (a jeho podstromu) urcuji PODILY mezi klienty.
    Skutecna fakturovana castka se vsak vzdy zadava do CostEntry
    pro dane obdobi - viz billing.engine.
    """

    class InvoiceClass(models.TextChoices):
        """
        Trida polozky odpovida radkum na vyslednem vyuctovani/fakture
        pro klienta - vzdy presne jedna z techto peti:
        """

        RENT = "rent", "Nájemné"
        ELECTRICITY = "electricity", "Elektřina"
        WATER = "water", "Voda"
        HEAT = "heat", "Teplo"
        OTHER = "other", "Ostatní"

    site = models.ForeignKey(
        "core.Site", on_delete=models.CASCADE, related_name="service_items", verbose_name="Areál"
    )
    unit = models.ForeignKey(
        Unit,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_items",
        verbose_name="Prostor",
        help_text="Volitelné - ke kterému prostoru se položka primárně vztahuje.",
    )
    meter = models.ForeignKey(
        Meter,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_items",
        verbose_name="Měřidlo",
        help_text="Vyplnit jen u měřených položek (energie).",
    )
    name = models.CharField("Název", max_length=200)
    invoice_class = models.CharField(
        "Třída",
        max_length=20,
        choices=InvoiceClass.choices,
        default=InvoiceClass.OTHER,
        help_text="Do které z 5 položek výsledné faktury tato položka spadá.",
    )

    class Meta:
        verbose_name = "Položka zásobníku"
        verbose_name_plural = "Zásobník"
        ordering = ["site", "invoice_class", "name"]

    def __str__(self):
        return f"{self.name} ({self.site})"


class AllocationKey(models.Model):
    """
    Klic - urcuje, jak se polozka Zasobniku rozpocita konkretni
    karte klienta.

    Typy:
    - percent: pevne procento (s pomerem dle aktivnich dni karty v obdobi)
    - area_ratio: dle vymery prostoru (m2) karty (s pomerem dle dni)
    - person_count: dle poctu osob (hodnota ve `value`, s pomerem dle dni)
    - equal_split: rovnym dilem mezi vsechny karty s timto klicem
    - submeter: 1:1 dle odectu konkretniho podruzneho meridla (`meter`)
    - fixed_amount: pevna castka (Kc) nezavisla na ostatnich - odecte
      se z celkove castky polozky a zbytek se rozpocita mezi ostatni
    """

    class AllocationType(models.TextChoices):
        PERCENT = "percent", "Procento"
        AREA_RATIO = "area_ratio", "Podle výměry (m²)"
        PERSON_COUNT = "person_count", "Podle počtu osob"
        EQUAL_SPLIT = "equal_split", "Rovným dílem"
        SUBMETER = "submeter", "Podružné měřidlo (1:1)"
        FIXED_AMOUNT = "fixed_amount", "Pevná částka"

    client_card = models.ForeignKey(
        ClientCard, on_delete=models.CASCADE, related_name="allocation_keys", verbose_name="Karta klienta"
    )
    service_item = models.ForeignKey(
        ServicePoolItem, on_delete=models.CASCADE, related_name="allocation_keys", verbose_name="Položka zásobníku"
    )
    allocation_type = models.CharField(
        "Typ rozpočtu", max_length=20, choices=AllocationType.choices
    )
    value = models.DecimalField(
        "Hodnota",
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Procento, počet osob nebo pevná částka (Kč) - dle typu.",
    )
    meter = models.ForeignKey(
        Meter,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submeter_keys",
        verbose_name="Podružné měřidlo",
        help_text="Pouze pro typ 'Podružné měřidlo (1:1)'.",
    )
    valid_from = models.DateField("Platnost od")
    valid_to = models.DateField("Platnost do", null=True, blank=True)

    class Meta:
        verbose_name = "Klíč"
        verbose_name_plural = "Klíče"
        ordering = ["service_item", "client_card"]

    def __str__(self):
        return f"{self.client_card} – {self.service_item} ({self.get_allocation_type_display()})"

    def clean(self):
        if self.allocation_type == self.AllocationType.SUBMETER and not self.meter_id:
            raise ValidationError("U typu 'Podružné měřidlo' je nutné vybrat měřidlo.")
        if self.allocation_type != self.AllocationType.SUBMETER and self.meter_id:
            raise ValidationError("Měřidlo se vyplňuje pouze u typu 'Podružné měřidlo'.")
        if self.allocation_type in (
            self.AllocationType.PERCENT,
            self.AllocationType.PERSON_COUNT,
            self.AllocationType.FIXED_AMOUNT,
        ) and self.value is None:
            raise ValidationError("U tohoto typu klíče je nutné vyplnit hodnotu.")
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError("Datum 'platnost do' nesmí být dříve než 'platnost od'.")

    def is_valid_for_period(self, period):
        period_start, period_end = period.date_range()
        if self.valid_from > period_end:
            return False
        if self.valid_to and self.valid_to < period_start:
            return False
        return True


class CostEntry(models.Model):
    """
    Skutecne naklady na polozku Zasobniku za dane obdobi - castka
    z faktury dodavatele (energie) nebo skutecny naklad (sluzby,
    napr. odklizeni snehu - v letnich mesicich nemusi existovat).
    """

    service_item = models.ForeignKey(
        ServicePoolItem, on_delete=models.CASCADE, related_name="cost_entries", verbose_name="Položka zásobníku"
    )
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, related_name="cost_entries", verbose_name="Období"
    )
    amount = models.DecimalField("Částka (Kč)", max_digits=14, decimal_places=2)
    note = models.CharField("Poznámka", max_length=300, blank=True)

    class Meta:
        verbose_name = "Náklad za období"
        verbose_name_plural = "Náklady za období"
        unique_together = ("service_item", "period")
        ordering = ["-period", "service_item"]

    def __str__(self):
        return f"{self.service_item} – {self.period}: {self.amount} Kč"


class BillingLine(models.Model):
    """Vysledny radek vyuctovani - castka pro konkretni kartu klienta,
    polozku a obdobi, vcetne detailu vypoctu pro auditovatelnost."""

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
    share = models.DecimalField(
        "Podíl", max_digits=8, decimal_places=6, null=True, blank=True,
        help_text="Podíl klienta na celkové částce (0-1), pokud relevantní.",
    )
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
        """Trida dle faktury (Najemne/Elektrina/Voda/Teplo/Ostatni) - zdedeno z polozky."""
        return self.service_item.invoice_class
