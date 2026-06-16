"""
Zakladni entity: arealy/objekty, pronajimane prostory, klienti
a jejich karty (najemni vztahy s platnosti).
"""
from django.core.exceptions import ValidationError
from django.db import models


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
    description = models.TextField("Popis", blank=True)

    class Meta:
        verbose_name = "Pronajímaný prostor"
        verbose_name_plural = "Pronajímané prostory"
        ordering = ["site", "name"]

    def __str__(self):
        return f"{self.site} – {self.name}"


class Client(models.Model):
    """Klient (najemce) - firma nebo osoba."""

    name = models.CharField("Název / jméno", max_length=200)
    ico = models.CharField("IČO", max_length=20, blank=True)
    dic = models.CharField("DIČ", max_length=20, blank=True)
    contact_email = models.EmailField("E-mail", blank=True)
    contact_phone = models.CharField("Telefon", max_length=50, blank=True)
    note = models.TextField("Poznámka", blank=True)

    class Meta:
        verbose_name = "Klient"
        verbose_name_plural = "Klienti"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ClientCard(models.Model):
    """
    Karta klienta - vazba klienta na konkretni pronajaty prostor
    s obdobim platnosti. Datumy valid_from/valid_to slouzi pro
    pomerne uctovani pri nastupu/odchodu v prubehu mesice.
    """

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="cards", verbose_name="Klient"
    )
    unit = models.ForeignKey(
        Unit, on_delete=models.CASCADE, related_name="cards", verbose_name="Prostor"
    )
    valid_from = models.DateField("Platnost od")
    valid_to = models.DateField("Platnost do", null=True, blank=True)
    note = models.TextField("Poznámka", blank=True)

    class Meta:
        verbose_name = "Karta klienta"
        verbose_name_plural = "Karty klientů"
        ordering = ["client", "valid_from"]

    def __str__(self):
        return f"{self.client} – {self.unit} ({self.valid_from} – {self.valid_to or 'trvá'})"

    def clean(self):
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError("Datum 'platnost do' nesmí být dříve než 'platnost od'.")

    def active_days_in_period(self, period_start, period_end):
        """
        Vrati pocet dni, po ktere byla karta aktivni v danem obdobi
        (vcetne obou krajnich dat). Pouziva se pro pomerne uctovani.
        """
        start = max(self.valid_from, period_start)
        end = min(self.valid_to or period_end, period_end)
        if end < start:
            return 0
        return (end - start).days + 1
