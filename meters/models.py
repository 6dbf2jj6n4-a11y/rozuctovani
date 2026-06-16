"""
Obdobi (kalendarni mesice), hierarchie meridel a jejich odecty.

Hierarchie meridel: kazde meridlo muze mit rodicovske meridlo
(parent). Spotreba na danem meridle se spocita jako rozdil
odectu mezi dvema obdobimi. Pro meridla s detmi se "spolecna"
(rezidualni) spotreba spocita jako vlastni spotreba minus soucet
spotreb vsech primych deti - viz billing.engine.
"""
import calendar
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models

from core.models import Site


class Period(models.Model):
    """Kalendarni mesic, za ktery se rozuctovava."""

    class Status(models.TextChoices):
        OPEN = "open", "Otevřeno"
        CLOSED = "closed", "Uzavřeno"

    year = models.PositiveIntegerField("Rok")
    month = models.PositiveSmallIntegerField("Měsíc")
    status = models.CharField(
        "Stav", max_length=10, choices=Status.choices, default=Status.OPEN
    )

    class Meta:
        verbose_name = "Období"
        verbose_name_plural = "Období"
        unique_together = ("year", "month")
        ordering = ["-year", "-month"]

    def __str__(self):
        return f"{self.month:02d}/{self.year}"

    def date_range(self):
        """Vrati (prvni_den, posledni_den) tohoto obdobi."""
        first_day = date(self.year, self.month, 1)
        last_day_num = calendar.monthrange(self.year, self.month)[1]
        last_day = date(self.year, self.month, last_day_num)
        return first_day, last_day

    @property
    def days_in_period(self):
        first_day, last_day = self.date_range()
        return (last_day - first_day).days + 1

    def previous_period(self):
        """Vrati predchazejici Period (pro vypocet spotreby), pokud existuje."""
        if self.month == 1:
            prev_year, prev_month = self.year - 1, 12
        else:
            prev_year, prev_month = self.year, self.month - 1
        return Period.objects.filter(year=prev_year, month=prev_month).first()


class Meter(models.Model):
    """
    Mericí bod (mericí). Mooze mit rodicovske meridlo (parent_meter) -
    napr. hlavni meridlo arealu -> podruzne meridlo -> podruzne
    podruzneho. Libovolna hloubka.
    """

    class MeterType(models.TextChoices):
        ELECTRICITY = "electricity", "Elektřina"
        WATER = "water", "Voda"
        GAS = "gas", "Plyn"
        HEAT = "heat", "Teplo"
        OTHER = "other", "Jiné"

    site = models.ForeignKey(
        Site, on_delete=models.CASCADE, related_name="meters", verbose_name="Areál"
    )
    parent_meter = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
        verbose_name="Nadřazené měřidlo",
        help_text="Prázdné = hlavní (fakturační) měřidlo pro tento areál a typ.",
    )
    name = models.CharField("Název / označení", max_length=200)
    meter_type = models.CharField(
        "Typ", max_length=20, choices=MeterType.choices
    )
    unit_of_measure = models.CharField(
        "Měrná jednotka", max_length=20, default="kWh"
    )
    serial_number = models.CharField("Výrobní číslo", max_length=100, blank=True)

    class Meta:
        verbose_name = "Měřidlo"
        verbose_name_plural = "Měřidla"
        ordering = ["site", "meter_type", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_meter_type_display()})"

    def clean(self):
        # Meridlo nemuze byt rodicem sama sebe a parent musi byt ve stejnem arealu
        if self.parent_meter_id and self.parent_meter_id == self.id:
            raise ValidationError("Měřidlo nemůže být nadřazené sobě samému.")
        if self.parent_meter_id and self.parent_meter and self.parent_meter.site_id != self.site_id:
            raise ValidationError("Nadřazené měřidlo musí být ve stejném areálu.")

    def reading_for(self, period):
        return self.readings.filter(period=period).first()

    def consumption_for(self, period):
        """
        Vlastni spotreba meridla za dane obdobi = aktualni odecet
        minus odecet z predchoziho obdobi. Vraci None, pokud chybi
        nektery z odectu.
        """
        current = self.reading_for(period)
        if current is None:
            return None
        prev_period = period.previous_period()
        if prev_period is None:
            return None
        previous = self.reading_for(prev_period)
        if previous is None:
            return None
        return current.value - previous.value


class MeterReading(models.Model):
    """Odecet meridla za dane obdobi."""

    meter = models.ForeignKey(
        Meter, on_delete=models.CASCADE, related_name="readings", verbose_name="Měřidlo"
    )
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE, related_name="readings", verbose_name="Období"
    )
    reading_date = models.DateField("Datum odečtu")
    value = models.DecimalField("Stav měřidla", max_digits=14, decimal_places=3)
    is_estimate = models.BooleanField(
        "Odhad",
        default=False,
        help_text="Zaškrtnout, pokud hodnota je odhad a bude později opravena.",
    )
    note = models.CharField("Poznámka", max_length=300, blank=True)

    class Meta:
        verbose_name = "Odečet měřidla"
        verbose_name_plural = "Odečty měřidel"
        unique_together = ("meter", "period")
        ordering = ["-period", "meter"]

    def __str__(self):
        return f"{self.meter} – {self.period}: {self.value}"
