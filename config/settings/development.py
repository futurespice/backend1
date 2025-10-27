from .base import *

DEBUG = True
load_dotenv()

# Development-specific apps
INSTALLED_APPS += [
    'django_extensions',
]

ALLOWED_HOSTS = ['*']

# Database берётся из base.py через DATABASE_URL

CORS_ALLOW_ALL_ORIGINS = True
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Redis из docker-compose
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://redis:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    }
}

CELERY_TASK_ALWAYS_EAGER = False  # Изменено на False для реального Celery
CELERY_TASK_EAGER_PROPAGATES = True
