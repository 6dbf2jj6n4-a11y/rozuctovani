"""
Vlastni uzivatelsky model s rolemi.

- admin: pristup ke vsemu (typicky majitel/sprava firmy)
- spravce: zadava odecty mericu a naklady, nevidi/neupravuje klice a sazby
- klient: vidi pouze sve karty, spotreby a vyuctovani (cteni)
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        SPRAVCE = "spravce", "Spravce"
        KLIENT = "klient", "Klient"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.KLIENT,
        verbose_name="Role",
    )

    # U uzivatelu s roli "klient" urcuje, ke kteremu klientovi (firme) patri
    # a tedy ktera data uvidi v klientskem portalu.
    client = models.ForeignKey(
        "core.Client",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
        verbose_name="Klient (firma)",
    )

    class Meta:
        verbose_name = "Uzivatel"
        verbose_name_plural = "Uzivatele"

    def __str__(self):
        return f"{self.get_username()} ({self.get_role_display()})"

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def is_spravce_role(self):
        return self.role in (self.Role.ADMIN, self.Role.SPRAVCE)
