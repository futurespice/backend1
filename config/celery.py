import os
from celery import Celery

# Django settings module для production
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

app = Celery('baielapp')

# Конфигурация из Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Автообнаружение задач из всех приложений
app.autodiscover_tasks()

# Настройки Celery
app.conf.update(
    broker_url=os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0'),
    result_backend=os.environ.get('REDIS_URL', 'redis://redis:6379/1'),
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Bishkek',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    worker_prefetch_multiplier=1,
)