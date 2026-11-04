import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("STASH_DATA", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = os.environ.get("DEBUG") == "1"
ORIGIN = os.environ.get("ORIGIN", "http://localhost:8000").rstrip("/")

ALLOWED_HOSTS = [urlparse(ORIGIN).hostname, "localhost", "127.0.0.1", "testserver"]
CSRF_TRUSTED_ORIGINS = [ORIGIN]
AUTH_MODE = os.environ.get("AUTH_MODE", "local")
assert AUTH_MODE in ("local", "oidc")
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
OIDC_OWNER_GROUP = os.environ.get("OIDC_OWNER_GROUP", "stash-owners")
OIDC_MEMBER_GROUP = os.environ.get("OIDC_MEMBER_GROUP", "stash-members")
CONDUCTOR_URL = os.environ.get("CONDUCTOR_URL", "")
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "inventory",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "inventory.middleware.Headers",
]
ROOT_URLCONF = "stash.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ]
        },
    }
]
WSGI_APPLICATION = "stash.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "stash.sqlite3",
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }
}
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = ORIGIN.startswith("https:")
SESSION_COOKIE_NAME = "__Host-stash" if SESSION_COOKIE_SECURE else "stash_session"
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 3600
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_ROOT = DATA_DIR / "photos"
MEDIA_ROOT.mkdir(exist_ok=True)
DATA_UPLOAD_MAX_MEMORY_SIZE = 32 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Operator controlled only. Never accept a printer address or executable from an API request.
PRINT_BRIDGE = os.environ.get("STASH_PRINT_BRIDGE", "/usr/local/bin/stash-print-bridge")
PRINTER_CONFIG = os.environ.get(
    "STASH_PRINTER_CONFIG", "/run/stash-printer/config.json"
)
STATION_FIRMWARE = os.environ.get(
    "STASH_STATION_FIRMWARE", "/run/stash-station/firmware.bin"
)
