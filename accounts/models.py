"""
Vlastni uzivatelsky model s rolemi.
- admin: pristup ke vsemu (typicky majitel/sprava firmy)
- spravce: zadava odecty mericu a naklady, nevidi/neupravuje klice a sazby
- klient: vidi pouze sve karty, spotreby a vyuctovani (cteni)
"""
from django.contrib.auth.models import AbstractUser
from django.db import models

from core.storage import R2MediaStorage


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrátor"
        SPRAVCE = "spravce", "Správce"
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
    # U uzivatelu s roli "spravce" urcuje, ke kterym arealum ma pristup.
    # Prazdne = pristup ke vsem arealum (pouziva se pro admina).
    sites = models.ManyToManyField(
        "core.Site",
        blank=True,
        related_name="managers",
        verbose_name="Areály",
        help_text="Areály ke kterým má správce přístup. Prázdné = přístup ke všem (admin).",
    )

    photo = models.ImageField(
        "Fotka", upload_to="uzivatele/", null=True, blank=True,
        storage=R2MediaStorage(),
        help_text=(
            "Zobrazí se v panelu přihlášeného uživatele dole v menu. "
            "Ideálně čtvercová, stačí malá (např. 200×200). Bez fotky se "
            "použije panáček."
        ),
    )

    class Meta:
        verbose_name = "Uživatel"
        verbose_name_plural = "Uživatelé"

    def __str__(self):
        return f"{self.get_username()} ({self.get_role_display()})"

    @property
    def photo_url(self):
        """Podepsana URL fotky, nebo None kdyz fotka neni / uloziste
        neodpovida.

        Fotka se kresli v panelu uzivatele, ktery je v bocnim menu na
        KAZDE strance adminu - vypadek nebo chybejici konfigurace R2 by
        tedy shodily cely admin, ne jen jednu stranku. Proto se chyba
        spolkne a panel spadne zpet na spolecny avatar/panacka. Lokalne
        (bez R2 promennych) to nastava vzdy, viz core/storage.py."""
        if not self.photo:
            return None
        try:
            return self.photo.url
        except Exception:
            return None

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def is_spravce_role(self):
        return self.role in (self.Role.ADMIN, self.Role.SPRAVCE)

    def get_accessible_sites(self):
        """Vrátí areály ke kterým má uživatel přístup."""
        from core.models import Site
        if self.is_admin_role or not self.sites.exists():
            return Site.objects.all()
        return self.sites.all()
