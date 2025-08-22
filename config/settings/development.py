from .base import *

DEBUG = True

# Development-specific apps
INSTALLED_APPS += [
    'django_extensions',  # pip install django-extensions
]

# Allow all hosts in development
ALLOWED_HOSTS = ['*']

# Database for development (SQLite)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# CORS settings for development
CORS_ALLOW_ALL_ORIGINS = True

# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Cache for development
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Celery settings for development
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True