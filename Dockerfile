FROM python:3.11-slim

# Системные зависимости
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        gcc \
        gettext \
        libpq-dev \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Пользователь для безопасности
RUN addgroup --system django \
    && adduser --system --ingroup django django

# Рабочая директория
WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект
COPY . /app/

# Создаем директории
RUN mkdir -p /app/logs /app/staticfiles /app/media

# Права на файлы
RUN chown -R django:django /app

# Переключаемся на django пользователя
USER django

# Порт
EXPOSE 8000

# Команда запуска
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]