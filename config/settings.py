"""
Konfigurace Django projektu "rozuctovani".
"""
import os
from datetime import date
from pathlib import Path

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-zmen-v-produkci")

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")


INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",
    "core",
    "meters",
    "billing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "config.middleware.SlowRequestLoggingMiddleware",
    "config.middleware.NonStaffAdminRedirectMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Databaze - pouzije prvni dostupnou konfiguraci
if os.environ.get("DJANGO_DB_ENGINE") == "sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
elif os.environ.get("DATABASE_URL"):
    import dj_database_url
    DATABASES = {
        "default": dj_database_url.config(conn_max_age=600, ssl_require=False)
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("PGDATABASE") or os.environ.get("POSTGRES_DB", "rozuctovani"),
            "USER": os.environ.get("PGUSER") or os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("PGPASSWORD") or os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("PGHOST") or os.environ.get("POSTGRES_HOST") or "postgres.railway.internal",
            "PORT": os.environ.get("PGPORT") or os.environ.get("POSTGRES_PORT", "5432"),
            # Bez tohohle se pro KAZDY request otevira nove DB spojeni od
            # nuly (Django CONN_MAX_AGE defaultne 0) - na Railway to
            # pridava plnou rezii TCP+Postgres handshake na uplne kazdou,
            # i tu nejjednodussi stranku v adminu. Viz konverzace
            # s Danielem - "kliknu na Obdobi a stranka najede za 5s".
            "CONN_MAX_AGE": 600,
        }
    }


AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


LANGUAGE_CODE = "cs"
TIME_ZONE = "Europe/Prague"
USE_I18N = True
USE_TZ = True
# Oddelovac tisicu v cislech (35 938,85 misto 35938.85) - ceske locale
# pouziva nezlomitelnou mezeru, stejne jako se to nastavuje v Excelu.
# Plati na cely admin i sablony. Viz konverzace s Danielem 2026-08-16.
USE_THOUSAND_SEPARATOR = True


STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
CSRF_TRUSTED_ORIGINS = [
    "https://rozuctovani-production.up.railway.app",
    "https://rentex-eu-production.up.railway.app",
    "https://rozuctovani.calamarise.eu",
]
# Django prepisuje radek session pri KAZDEM pozadavku, ne jen kdyz se
# session zmeni. Dve veci z toho plynou:
#   1) django_session.expire_date je vzdycky "cas posledniho pozadavku +
#      SESSION_COOKIE_AGE", takze se z nej da poznat, kdo je prave ted
#      aktivni - to pohani cislo v kolecku loga v hlavicce menu
#      (core.templatetags.core_extras.pocet_prihlasenych),
#   2) platnost prihlaseni se pri praci sama prodluzuje, takze aktivniho
#      uzivatele uz aplikace po 14 dnech neodhlasi uprostred prace.
# Cenou je jeden zapis do databaze navic na pozadavek - pri hrstce
# uzivatelu zanedbatelne. Dohoda s Danielem 2026-08-24.
SESSION_SAVE_EVERY_REQUEST = True

# Verze zobrazena v hlavicce adminu - APP_VERSION_SEQUENCE se zvysuje
# o +1 po kazdem commitu a pushi (dohoda s Danielem 2026-08-09), format
# RRRR.poradove_cislo, napr. 2026.1 -> 2026.2 -> 2026.3... Rok se BERE
# AUTOMATICKY (date.today().year), takze pri prechodu na dalsi
# kalendarni rok se poradove cislo samo restartuje na 0 (2026.87 ->
# 2027.0), i kdyby se nekdo zapomnel APP_VERSION_YEAR rucne prepsat -
# dohoda s Danielem 2026-08-15.
APP_VERSION_YEAR = 2026
APP_VERSION_SEQUENCE = 180
APP_VERSION = (
    f"{APP_VERSION_YEAR}.{APP_VERSION_SEQUENCE}"
    if date.today().year == APP_VERSION_YEAR
    else f"{date.today().year}.0"
)

UNFOLD = {
    "SITE_TITLE": "RENTE)(",
    "SITE_HEADER": f"Rente )( {APP_VERSION}",
    "SITE_ICON": "core.admin_branding.site_icon",
    "SITE_SUBHEADER": "core.admin_branding.site_subheader",
    "STYLES": [
        "core.admin_branding.inline_date_width_fix_css",
        "core.admin_branding.class_colors_css",
        "core.admin_branding.report_filters_css",
        "core.admin_branding.changelist_header_wrap_css",
        "core.admin_branding.sidebar_extras_css",
        "core.admin_branding.buttons_css",
        "core.admin_branding.planky_css",
        "core.admin_branding.odkazy_css",
        "core.admin_branding.sekce_css",
    ],
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Období"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Období"),
                        "icon": "calendar_month",
                        "link": reverse_lazy("admin:core_period_changelist"),
                    },
                    {
                        "title": _("Náklady za období"),
                        "icon": "payments",
                        "link": reverse_lazy("admin:core_costentry_changelist"),
                    },
                    {
                        "title": _("Ceníky"),
                        "icon": "sell",
                        "link": reverse_lazy("admin:core_pricelist_changelist"),
                    },
                    {
                        "title": _("Odečty měřidel"),
                        "icon": "speed",
                        "link": reverse_lazy("admin:core_meterreading_changelist"),
                    },
                    {
                        "title": _("Míry inflace"),
                        "icon": "trending_up",
                        "link": reverse_lazy("admin:core_inflationrate_changelist"),
                    },
                ],
            },
            {
                "title": _("Areály/Objekty"),
                "separator": True,
                # Sbalovatelna sekce (nativni funkce Unfoldu) - menu ma pres
                # 30 polozek a muselo se rolovat. Sekce, ve ktere je prave
                # otevrena stranka, se rozbali sama (has_nav_item_active),
                # takze se uzivatel nikam neproklikava navic. Sbaluji se
                # VSECHNY sekce - Daniel si to tak vyzadal 2026-08-19
                # (puvodne zustavaly Období a Klienti trvale otevrene).
                "collapsible": True,
                "items": [
                    {
                        "title": _("Areály/Objekty"),
                        "icon": "domain",
                        "link": reverse_lazy("admin:core_site_changelist"),
                    },
                    {
                        "title": _("Pronajímané prostory"),
                        "icon": "meeting_room",
                        "link": reverse_lazy("admin:core_unit_changelist"),
                    },
                    {
                        "title": _("Plánky"),
                        "icon": "map",
                        "link": reverse_lazy("admin:core_floorplan_changelist"),
                    },
                    {
                        "title": _("Kontrola plánků"),
                        "icon": "rule",
                        "link": reverse_lazy("admin:core_floorplan_kontrola"),
                    },
                    {
                        "title": _("Třídy"),
                        "icon": "category",
                        "link": reverse_lazy("admin:core_invoiceclasscolor_changelist"),
                    },
                    {
                        "title": _("Měřidla"),
                        "icon": "speed",
                        "link": reverse_lazy("admin:core_meter_changelist"),
                    },
                    {
                        "title": _("Odběrná místa"),
                        "icon": "bolt",
                        "link": reverse_lazy("admin:core_supplypoint_changelist"),
                    },
                    {
                        "title": _("Zásobník služeb"),
                        "icon": "inventory_2",
                        "link": reverse_lazy("admin:core_servicepoolitem_changelist"),
                    },
                ],
            },
            {
                "title": _("Klienti"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Klienti"),
                        "icon": "groups",
                        "link": reverse_lazy("admin:core_client_changelist"),
                    },
                    {
                        "title": _("Smlouvy"),
                        "icon": "description",
                        "link": reverse_lazy("admin:core_contract_changelist"),
                    },
                    {
                        "title": _("Karty klientů"),
                        "icon": "badge",
                        "link": reverse_lazy("admin:core_clientcard_changelist"),
                    },
                    {
                        "title": _("Klíče"),
                        "icon": "key",
                        "link": reverse_lazy("admin:core_allocationkey_changelist"),
                    },
                ],
            },
            {
                "title": _("Vyúčtování"),
                "separator": True,
                # Sbalovatelna sekce (nativni funkce Unfoldu) - menu ma pres
                # 30 polozek a muselo se rolovat. Sekce, ve ktere je prave
                # otevrena stranka, se rozbali sama (has_nav_item_active),
                # takze se uzivatel nikam neproklikava navic. Sbaluji se
                # VSECHNY sekce - Daniel si to tak vyzadal 2026-08-19
                # (puvodne zustavaly Období a Klienti trvale otevrene).
                "collapsible": True,
                "items": [
                    {
                        "title": _("Položky"),
                        "icon": "receipt_long",
                        "link": reverse_lazy("admin:core_billingline_changelist"),
                    },
                    {
                        "title": _("Detail"),
                        "icon": "query_stats",
                        "link": reverse_lazy("admin:core_billingline_detail"),
                    },
                    {
                        "title": _("Náklad/Výnos"),
                        "icon": "account_balance",
                        "link": reverse_lazy("admin:core_billingline_prehled"),
                    },
                    {
                        "title": _("Náklad/Výnos – měřidla"),
                        "icon": "speed",
                        "link": reverse_lazy("admin:core_billingline_prehled_meridla"),
                    },
                    {
                        "title": _("Podíl vah"),
                        "icon": "pie_chart",
                        "link": reverse_lazy("admin:core_billingline_podil_vah"),
                    },
                    {
                        "title": _("Vyúčtování klienta"),
                        "icon": "receipt",
                        "link": reverse_lazy("moje-vyuctovani"),
                    },
                ],
            },
            {
                "title": _("Reporty"),
                "separator": True,
                # Sbalovatelna sekce (nativni funkce Unfoldu) - menu ma pres
                # 30 polozek a muselo se rolovat. Sekce, ve ktere je prave
                # otevrena stranka, se rozbali sama (has_nav_item_active),
                # takze se uzivatel nikam neproklikava navic. Sbaluji se
                # VSECHNY sekce - Daniel si to tak vyzadal 2026-08-19
                # (puvodne zustavaly Období a Klienti trvale otevrene).
                "collapsible": True,
                "items": [
                    {
                        "title": _("Plochy s více klienty"),
                        "icon": "warning",
                        "link": reverse_lazy("admin:core_clientcard_report_plochy_konflikt"),
                    },
                    {
                        "title": _("Přehled nájemného"),
                        "icon": "payments",
                        "link": reverse_lazy("admin:core_clientcard_report_najemne"),
                    },
                    {
                        "title": _("Nepřiřazená měřidla"),
                        "icon": "speed",
                        "link": reverse_lazy("admin:core_meter_report_neprirazena"),
                    },
                    {
                        "title": _("Spotřeby dle hierarchie"),
                        "icon": "account_tree",
                        "link": reverse_lazy("admin:core_meter_report_spotreby"),
                    },
                    {
                        "title": _("Grafy nákladů dle tříd"),
                        "icon": "bar_chart",
                        "link": reverse_lazy("admin:core_billingline_report_grafy_trid"),
                    },
                    {
                        "title": _("Kontakty klientů"),
                        "icon": "contacts",
                        "link": reverse_lazy("admin:core_client_report_kontakty"),
                    },
                    {
                        "title": _("Paušální klienti"),
                        "icon": "balance",
                        "link": reverse_lazy("admin:core_billingline_report_pausalni"),
                    },
                ],
            },
            {
                "title": _("Správa uživatelů"),
                "separator": True,
                # Sbalovatelna sekce (nativni funkce Unfoldu) - menu ma pres
                # 30 polozek a muselo se rolovat. Sekce, ve ktere je prave
                # otevrena stranka, se rozbali sama (has_nav_item_active),
                # takze se uzivatel nikam neproklikava navic. Sbaluji se
                # VSECHNY sekce - Daniel si to tak vyzadal 2026-08-19
                # (puvodne zustavaly Období a Klienti trvale otevrene).
                "collapsible": True,
                "items": [
                    {
                        "title": _("Uživatelé"),
                        "icon": "manage_accounts",
                        "link": reverse_lazy("admin:accounts_user_changelist"),
                    },
                ],
            },
        ],
    },
}
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "DEBUG" if DEBUG else "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}
