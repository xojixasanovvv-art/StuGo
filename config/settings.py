"""
Django settings for the StuGo project.

Lokal ishlash uchun .env faylini .env.example asosida to'ldirish kerak.
Production'da quyidagilar majburiy:
    SECRET_KEY, DEBUG=False, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS,
    CORS_ALLOWED_ORIGINS, REDIS_URL, DB_* (PostgreSQL)
"""

import atexit
import os
import shutil
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    return str(os.environ.get(key, default)).lower() in {"1", "true", "yes", "on"}


def env_list(key, default=""):
    return [i.strip() for i in str(os.environ.get(key, default)).split(",") if i.strip()]


# Test rejimini erta aniqlaymiz (settings yuklanishidan oldin kerak)
TESTING = "test" in sys.argv

# ---------------------------------------------------------------------------
# Xavfsizlik asoslari
# ---------------------------------------------------------------------------

# SECURITY WARNING: production'da SECRET_KEY .env orqali MAJBURIY berilishi shart.
SECRET_KEY = env("SECRET_KEY")
DEBUG = env_bool("DEBUG", False)

if not SECRET_KEY:
    if TESTING:
        SECRET_KEY = "test-only-insecure-key-not-for-production"
    elif DEBUG:
        # Lokal rivojlashda tasodifiy kalit yaratiladi (har restartda o'zgaradi).
        import secrets as _secrets

        SECRET_KEY = _secrets.token_urlsafe(64)
        import warnings

        warnings.warn(
            "SECRET_KEY .env'da yo'q. Lokal uchun tasodifiy kalit yaratildi — "
            "bu kalit restartda o'zgaradi. Production uchun .env'ga yozing.",
            RuntimeWarning,
        )
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY .env faylida yoki muhit o'zgaruvchisida belgilanmagan. "
            "Production'da bu majburiy."
        )

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,[::1]")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    # Channels 4: runserver ASGI (WebSocket) rejimiga o'tishi uchun birinchi bo'lishi shart
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 3rd party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    # Loyiha ilovalari
    "apps.core",
    "apps.users",
    "apps.housing",
    "apps.roommates",
    "apps.chat",
    "apps.notifications",
    "apps.reports",
    "apps.shop",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # CORS eng yuqorida bo'lishi shart (CommonMiddleware'dan oldin)
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # LocaleMiddleware CommonMiddleware'dan KEYIN bo'lishi shart: u
    # `request.LANGUAGE_CODE` ni belgilaydi va `LANGUAGE_CODE` ni
    # har so'rovda active bo'lib qolishiga yo'l beradi.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # `?lang=ru` va `X-StuGo-Language` sarlavhasini qo'llab-quvvatlaydi
    # (cookie'siz API so'rovlari uchun). Cookie'ni esa `LocaleMiddleware`
    # o'zi o'qiydi — alohida middleware kerak emas.
    "apps.core.middleware.ApiLocaleMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# CORS — frontend boshqa origin'da (React/Next) ishga tushayotgani uchun
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CORS_URLS_REGEX = r"^/api/.*$"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

REDIS_URL = env("REDIS_URL")

if env("DB_NAME"):
    # PostgreSQL (tz.txt'da ko'rsatilgan production stack)
    DATABASES = {
        "default": {
            "ENGINE": env("DB_ENGINE", "django.db.backends.postgresql"),
            "NAME": env("DB_NAME"),
            "USER": env("DB_USER", ""),
            "PASSWORD": env("DB_PASSWORD", ""),
            "HOST": env("DB_HOST", "localhost"),
            "PORT": env("DB_PORT", "5432"),
            "CONN_MAX_AGE": int(env("DB_CONN_MAX_AGE", "60")),
        }
    }
else:
    # Lokal ishlash uchun SQLite fallback
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Cache va Channels
#
# Eslatma: OTP kodlari va throttle hisoblari cache'da saqlanadi. LocMemCache
# ko'p ishchi jarayon (daphne worker) holatida bo'linmaydi — production uchun
# REDIS_URL majburiy.
# ---------------------------------------------------------------------------

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# ---------------------------------------------------------------------------
# Internationalization — 3 til: uz / ru / en
# ---------------------------------------------------------------------------
#
# Til tanlash tartibi (birinchi mavjud bo'lgani qo'llaniladi):
#   1. URL:  /?lang=ru   yoki  /ru/ prefiksi
#   2. Cookie: `stugo_lang` (LanguageCookieMiddleware yozadi, 1 yil)
#   3. `Accept-Language` sarlavhasi
#   4. `LANGUAGE_CODE` (default: uz)
#
# Muhim: DRF API so'rovlari uchun ham til ishlashi kerak. Buning uchun
# `ApiLocaleMiddleware` (apps.core.middleware) `?lang=` va `Accept-Language`
# dan foydalanib `request.LANGUAGE_CODE` ni o'rniga qo'yadi — chunki API
# so'rovlarida cookie har doim yuborilmaydi.

LANGUAGES = [
    ("uz", "O'zbekcha"),
    ("ru", "Русский"),
    ("en", "English"),
]

LANGUAGE_CODE = env("LANGUAGE_CODE", "uz")
TIME_ZONE = env("TIME_ZONE", "Asia/Tashkent")
USE_I18N = True
USE_TZ = True
USE_I18N_TEMPLATES_EXTENSION = True

# Tarjima kataloglari. Ikki manba birga ishlatiladi:
#  1) `locale/<lang>/LC_MESSAGES/django.po` — Django/DRF/admin matnlari
#     (standart `makemessages`/`compilemessages` jarayoni).
#  2) `locale/frontend/<lang>.json` — interfeys matnlari uchun.
#     Bu fayl ham HTML shablonlari, ham JavaScript orqali ishlatiladi
#     (inline JS da `t("key")` funksiyasi orqali).
LOCALE_PATHS = [BASE_DIR / "locale"]

# Cookie nomi va umr davomiyligi (yil)
LANGUAGE_COOKIE_NAME = "stugo_lang"
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365

# Interfeys tarjimalari JSON fayllari papkasi
FRONTEND_LOCALE_DIR = BASE_DIR / "locale" / "frontend"

# ---------------------------------------------------------------------------
# Static va media fayllar
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Testlar paytida yuklangan fayllar vaqtinchalik papkaga tushadi
if TESTING:
    MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="stugo-test-media-"))
    atexit.register(shutil.rmtree, MEDIA_ROOT, ignore_errors=True)

# ---------------------------------------------------------------------------
# HTTP xavfsizligi (production uchun)
# ---------------------------------------------------------------------------

SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)

# Production'da (DEBUG=False) HTTPS majburiy. Lokal ishlashda o'chiriladi,
# aks holda `http://localhost` so'rovlari 301 ga ketadi va devtools
# chalkashadi. Reverse proxy (nginx) oldida `SECURE_PROXY_SSL_HEADER`
# orqali `X-Forwarded-Proto` hisobga olinadi.
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
# HSTS faqat haqiqiy HTTPS domainida yoqiladi — localhost/127.0.0.1 uchun
# HSTS brauzerda kesholmaydi va testlarga zarar beradi.
_SECURE_TRANSPORT = not DEBUG and not env_bool("LOCAL_HTTP", False)
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000" if _SECURE_TRANSPORT else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", _SECURE_TRANSPORT
)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", _SECURE_TRANSPORT)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Celery (background tasklar)
# ---------------------------------------------------------------------------
# Broker Redis bo'lmasa tasklar yuborilmaydi — bu normal, API ishlayveradi.

CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL or "memory://")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", REDIS_URL or "cache+memory://")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 10

# ---------------------------------------------------------------------------
# Custom user model
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "users.User"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Eslatma: DEFAULT_THROTTLE_RATES faqat throttle_scope belgilangan
    # viewlarda qo'llaniladi. scopes viewlar ustida ko'rsatilgan.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "otp_send": env("THROTTLE_OTP_SEND", "5/hour"),
        "otp_verify": env("THROTTLE_OTP_VERIFY", "10/hour"),
        "message_send": env("THROTTLE_MESSAGE_SEND", "60/hour"),
        "listing_create": env("THROTTLE_LISTING_CREATE", "20/day"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_MINUTES", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("JWT_REFRESH_DAYS", "30"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "StuGo API",
    "DESCRIPTION": "StuGo — studentlar ekotizimi platformasi API'si.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # `type`/`status`/`gender` maydonlari bir nechta modelda takrorlanadi.
    # Aniq nom berilsa, schema'dagi `Type4c7Enum` kabi tasodifiy nomlar
    # paydo bo'lmaydi.
    "ENUM_NAME_OVERRIDES": {
        "ListingTypeEnum": "apps.housing.models.listing.ListingType.choices",
        "ListingStatusEnum": "apps.housing.models.listing.ListingStatus.choices",
        "GenderEnum": "apps.core.enums.Gender.choices",
        # Ichki (nested) `Status` klasslari — `.choices` emas, klassning
        # o'zi ko'rsatiladi (drf-spectacular `Choices` ni o'zi ochadi).
        "ReportStatusEnum": "apps.reports.models.Report.Status",
        "MatchStatusEnum": "apps.roommates.models.match.Match.Status",
        "VerificationStatusEnum": "apps.users.models.VerificationStatus.choices",
        "VerificationMethodEnum": "apps.users.models.VerificationMethod.choices",
    },
    # Production'da API sxemasi ommaviy bo'lishi kerak emas
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"]
    if DEBUG
    else ["rest_framework.permissions.IsAdminUser"],
}

# ---------------------------------------------------------------------------
# OTP sozlamalari
# ---------------------------------------------------------------------------

OTP_LENGTH = int(env("OTP_LENGTH", "6"))
OTP_EXPIRE_SECONDS = int(env("OTP_EXPIRE_SECONDS", "300"))
OTP_MAX_ATTEMPTS = int(env("OTP_MAX_ATTEMPTS", "5"))
OTP_RESEND_COOLDOWN_SECONDS = int(env("OTP_RESEND_COOLDOWN_SECONDS", "30"))

# OTP kodini API javobida qaytarish. FAQAT lokal rivojlash uchun.
# Production'da DEBUG True bo'lishi ham yetarli emas — aniq opt-in kerak.
OTP_DEBUG_RETURN_CODE = env_bool("OTP_DEBUG_RETURN_CODE") and DEBUG

# Telefon operator kodlari. `apps.users.services` da O'zbekistondagi barcha
# rasmiy mobil/region kodlari allaqachon bor. Bu qiymat faqat QUSHIMCHA
# kodlar uchun — masalan yangi operator chiqsa, kodga tegmasdan shu yerga
# yozish yetarli. Vergul bilan ajratiladi.
# Namuna: PHONE_OPERATOR_CODES=20,21,22
PHONE_OPERATOR_CODES = env("PHONE_OPERATOR_CODES", "")

# Universitet email domenlari — vergul bilan ajratilgan.
# Domain tekshiruvi "endswith" emas, aniq "@" dan keyingi qism parse qilinadi.
UNIVERSITY_EMAIL_DOMAINS = env_list(
    "UNIVERSITY_EMAIL_DOMAINS",
    # `.env` yozilmagan holatda ham asosiy OTM domenlari ishlashi uchun
    # default ro'yxat kengaytirilgan (taxminiy universitet subdomenlari).
    "uz, ut.uz, uz.uz, web.uz, natlib.uz, umma.uz, uzm.uz, "
    "tuit.uz, ntuit.uz, newuu.uz, ntu.uz, tu.uz, webmail.uz, "
    "sdu.uz, andijon.uz, buxoro.uz, namangan.uz, jizzakh.uz, "
    "sirdaryo.uz, surxondaryo.uz, kashkadaryo.uz, khorazm.uz, "
    "tashkent.uz, qarshi.uz, termez.uz, gdu.uz, uzbekistan.uz",
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": env("LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}