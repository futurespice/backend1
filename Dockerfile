# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        gcc \
        gettext \
        git \
        libpq-dev \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Создаем пользователя для безопасности
RUN addgroup --system django \
    && adduser --system --ingroup django django

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект
COPY . /app/

# Создаем необходимые директории
RUN mkdir -p /app/logs /app/staticfiles /app/media

# Устанавливаем права на файлы
RUN chown -R django:django /app

# Переключаемся на пользователя django
USER django

# Собираем статику
RUN python manage.py collectstatic --noinput

# Открываем порт
EXPOSE 8000

# Команда по умолчанию
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]