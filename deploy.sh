#!/bin/bash

# Простой деплой Django в Docker

set -e

echo "🚀 Starting deployment..."

# Остановка контейнеров
docker-compose down

# Создание локальных директорий
mkdir -p data staticfiles media

# Сборка и запуск
docker-compose up --build -d

echo "✅ Deployment completed!"
echo "🌐 Django running on: http://localhost:8000"
echo "📊 Admin: http://localhost:8000/admin (admin@example.com / admin123)"
echo "📚 API docs: http://localhost:8000/api/docs"
echo ""
echo "🔧 Configure your Nginx to proxy to localhost:8000"