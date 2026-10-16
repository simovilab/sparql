"""Production overrides loaded by the upstream QLever UI Django settings."""

# Traefik is the only public ingress and sets X-Forwarded-Proto itself.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# The upstream formatter template passes "/wasm/..." to {% static %}, while
# collectstatic's manifest correctly stores "wasm/...". Keep hashed assets
# and DEBUG=False, but normalize that leading slash before the lookup.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "qlever.production_storage.NormalizedManifestStorage"},
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
