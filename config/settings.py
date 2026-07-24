"""
Konfigurace Django projektu "rozuctovani".
"""
import os
from pathlib import Path

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-zmen-v-produkci")

DEBUG = True

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
        }
    }


AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "moje-vyuctovani"
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
]
UNFOLD = {
    "SITE_TITLE": "RENTE)(",
    "SITE_HEADER": "RENTEX_2026",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Období"),
                "separator": True,
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
                        "title": _("Měřidla"),
                        "icon": "speed",
                        "link": reverse_lazy("admin:core_meter_changelist"),
                    },
                ],
            },
            {
                "title": _("Klienti"),
                "separator": True,
                "items": [
                    {
                        "title": _("Klienti"),
                        "icon": "groups",
                        "link": reverse_lazy("admin:core_client_changelist"),
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
                    {
                        "title": _("Smlouvy"),
                        "icon": "description",
                        "link": reverse_lazy("admin:core_contract_changelist"),
                    },
                ],
            },
            {
                "title": _("Vyúčtování"),
                "separator": True,
                "items": [
                    {
                        "title": _("Ceníky"),
                        "icon": "sell",
                        "link": reverse_lazy("admin:core_pricelist_changelist"),
                    },
                    {
                        "title": _("Položky"),
                        "icon": "receipt_long",
                        "link": reverse_lazy("admin:core_billingline_changelist"),
                    },
                    {
                        "title": _("Zásobník"),
                        "icon": "inventory_2",
                        "link": reverse_lazy("admin:core_servicepoolitem_changelist"),
                    },
                ],
            },
            {
                "title": _("Správa uživatelů"),
                "separator": True,
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
        "level": "DEBUG",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
