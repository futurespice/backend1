from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()

# Основные ViewSets
router.register(r'categories', views.ProductCategoryViewSet)
router.register(r'images', views.ProductImageViewSet)
router.register(r'products', views.ProductViewSet)  # Явно указываем префикс

app_name = 'products'

urlpatterns = [
    path('', include(router.urls)),
]