from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    StoreViewSet, StoreRequestViewSet, ProductCatalogView, StoreInventoryViewSet
)

router = DefaultRouter()
router.register(r'stores', StoreViewSet, basename='stores')
router.register(r'requests', StoreRequestViewSet, basename='store-requests')
router.register(r'inventory', StoreInventoryViewSet, basename='store-inventory')

urlpatterns = [
    # Каталог товаров для магазинов
    path('catalog/', ProductCatalogView.as_view(), name='product-catalog'),

    # Роуты ViewSet'ов
    path('', include(router.urls)),
]