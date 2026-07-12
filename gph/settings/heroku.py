import os

import dj_database_url

from .base import *

DEBUG = False
IS_TEST = False

# Set this via: heroku config:set DOMAIN=https://your-app.herokuapp.com/
DOMAIN = os.environ.get('DOMAIN', 'https://your-app.herokuapp.com/')

# Comma-separated list of allowed hosts, e.g. "yourhunt.herokuapp.com,yourdomain.com"
# Set via: heroku config:set ALLOWED_HOSTS=your-app.herokuapp.com
_allowed = os.environ.get('ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(',') if h.strip()] or ['.herokuapp.com']

# Database — automatically configured from DATABASE_URL set by Heroku Postgres addon
DATABASES = {
    'default': dj_database_url.config(conn_max_age=600, ssl_require=True)
}

# Redis — automatically configured from REDIS_URL set by Heroku Redis addon
REDIS_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    }
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [REDIS_URL],
        },
    }
}

# Static files served by WhiteNoise
# WhiteNoise must come immediately after SecurityMiddleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.http.ConditionalGetMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'impersonate.middleware.ImpersonateMiddleware',
    'puzzles.messaging.log_request_middleware',
    'puzzles.context.context_middleware',
    'puzzles.puzzlehandlers.reverse_proxy_middleware',
    'puzzles.views.accept_ranges_middleware',
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
# Use 'staticfiles' to distinguish collected files from source 'static' directories
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Heroku captures stdout/stderr — log to console instead of files
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s (PID %(process)d) [%(levelname)s] %(name)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'puzzles': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
