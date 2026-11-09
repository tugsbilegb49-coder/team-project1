"""Development settings for the Worker Activity Monitor API."""

from pathlib import Path
from datetime import timedelta
import os
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Override in deployment with a long, private environment variable.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-this-secret-key-before-deployment")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
if not DEBUG and (len(SECRET_KEY) < 50 or SECRET_KEY.startswith(('dev-only-', 'replace-'))):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('Production requires a private random DJANGO_SECRET_KEY of at least 50 characters.')
ALLOWED_HOSTS = [host for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "users",
    "workforce",
    "activity",
    "scoring",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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
        "DIRS": [],
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

if os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ.get("POSTGRES_USER", "worker_monitor"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "db"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Ulaanbaatar"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "users.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_RATES": {
        "login_ip": "10/min",
        "login_account": "20/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Monitoring collection requires a recorded, active consent by default.
REQUIRE_MONITORING_CONSENT = os.environ.get("REQUIRE_MONITORING_CONSENT", "true").lower() == "true"
ACTIVITY_RETENTION_DAYS = int(os.environ.get("ACTIVITY_RETENTION_DAYS", "90"))
ACTIVITY_RETENTION_AUTO = os.environ.get("ACTIVITY_RETENTION_AUTO", "true").lower() == "true"
BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "7"))
if ACTIVITY_RETENTION_DAYS < 1:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("ACTIVITY_RETENTION_DAYS must be at least 1.")
if BACKUP_KEEP < 1:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("BACKUP_KEEP must be at least 1.")
CORS_ALLOWED_ORIGINS = [origin for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if origin]
CSRF_TRUSTED_ORIGINS = [origin for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if origin]
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "false").lower() == "true"


# Server-side allowlist for the aggregate activity_agent contract. Browsers
# are not productive by default; configure explicitly for your team's work.
PRODUCTIVE_APPLICATIONS = [name.strip() for name in os.environ.get(
    "PRODUCTIVE_APPLICATIONS",
    "Visual Studio Code,Code,PyCharm,Terminal,iTerm2,Microsoft Word,WINWORD,Microsoft Excel,EXCEL,Microsoft PowerPoint,POWERPNT,Numbers,Pages,Keynote,Figma,Notion",
).split(",") if name.strip()]

TRUSTED_PROXY_NETWORKS = [value.strip() for value in os.environ.get('TRUSTED_PROXY_NETWORKS','').split(',') if value.strip()]
if os.environ.get('DJANGO_CACHE_BACKEND') == 'database':
    CACHES = {'default': {'BACKEND':'django.core.cache.backends.db.DatabaseCache','LOCATION':'worktrack_cache','OPTIONS':{'MAX_ENTRIES':100000}}}
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
if os.environ.get('TRUST_PROXY_HEADERS','false').lower() == 'true':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO','https')
LOGGING = {
    'version':1,'disable_existing_loggers':False,
    'handlers':{'console':{'class':'logging.StreamHandler'}},
    'root':{'handlers':['console'],'level':os.environ.get('DJANGO_LOG_LEVEL','WARNING')},
}
