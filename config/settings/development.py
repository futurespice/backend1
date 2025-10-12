from .base import *

DEBUG = True
load_dotenv()
# Development-specific apps
INSTALLED_APPS += [
    'django_extensions',  # pip install django-extensions
]

# Allow all hosts in development
ALLOWED_HOSTS = ['*']

# DATABASES = {
#     'default': dj_database_url.parse(
#         os.environ.get('DATABASE_URL', 'postgres://baeil_app:12345678@db:5432/baielapp_2')
#     )
# }
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'baielapp_2',
#         'USER': 'baiel_app',
#         'PASSWORD': '12345678',
#         'HOST': 'localhost',  # Локальный хост вместо 'db'
#         'PORT': '5432',
#     }
# }


# CORS settings for development
CORS_ALLOW_ALL_ORIGINS = True

# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

# Cache for development
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Celery settings for development
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

