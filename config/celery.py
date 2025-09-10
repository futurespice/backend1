# config/celery.py

import os
from celery import Celery

# Устанавливаем переменную окружения для настроек Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development') # Укажите ваш путь к настройкам

app = Celery('config')

# Используем конфигурацию из настроек Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Автоматически находим все файлы tasks.py в ваших приложениях
app.autodiscover_tasks()