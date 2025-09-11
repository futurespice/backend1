from django.urls import path, include
from rest_framework.routers import DefaultRouter

# Пока нет views, создаем пустой роутер
router = DefaultRouter()

app_name = 'reports'

urlpatterns = [
    path('', include(router.urls)),
]
