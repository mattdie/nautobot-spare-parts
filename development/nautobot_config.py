"""Nautobot settings for the spare-parts test environment.

Mirrors the EEN test cluster version (3.0.11) with the smallest possible set of
overrides: everything else comes from Nautobot's own defaults, driven by the
NAUTOBOT_* variables in dev.env.
"""

import os

from nautobot.core.settings import *  # noqa: F401,F403
from nautobot.core.settings_funcs import parse_redis_connection

SECRET_KEY = os.environ["NAUTOBOT_SECRET_KEY"]
ALLOWED_HOSTS = ["*"]
DEBUG = True
INSTALLATION_METRICS_ENABLED = False

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": parse_redis_connection(redis_database=1),
        "TIMEOUT": 300,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}
CELERY_BROKER_URL = parse_redis_connection(redis_database=0)

# `nautobot-server check --deploy` runs on every container start and these are
# all "you are not running behind TLS" warnings, which is correct and expected
# for a local test container.
SILENCED_SYSTEM_CHECKS = [
    "security.W004",
    "security.W008",
    "security.W009",
    "security.W012",
    "security.W016",
    "security.W018",
]

PLUGINS = ["nautobot_spare_parts"]
PLUGINS_CONFIG = {
    "nautobot_spare_parts": {},
}

# Show every app log line in `./dev logs`, and don't swallow tracebacks.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "loggers": {
        "nautobot": {"handlers": ["console"], "level": os.getenv("NAUTOBOT_LOG_LEVEL", "INFO")},
        "nautobot_spare_parts": {"handlers": ["console"], "level": "DEBUG"},
        "django.request": {"handlers": ["console"], "level": "ERROR"},
    },
}
