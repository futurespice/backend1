FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gettext \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/staticfiles /app/media /app/data

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=config.settings.development

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
