# apps/stores/urls.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegionViewSet, CityViewSet, StoreViewSet, StoreSelectionViewSet,
    StoreProductRequestViewSet, StoreRequestViewSet,
    StoreInventoryViewSet, PartnerInventoryViewSet, ReturnRequestViewSet
)

router = DefaultRouter()

# ИСПРАВЛЕНИЕ #4: Добавлен CityViewSet
router.register(r'regions', RegionViewSet, basename='regions')
router.register(r'cities', CityViewSet, basename='cities')
router.register(r'stores', StoreViewSet, basename='stores')
router.register(r'selection', StoreSelectionViewSet, basename='store-selection')
router.register(r'product-requests', StoreProductRequestViewSet, basename='product-requests')
router.register(r'requests', StoreRequestViewSet, basename='store-requests')
router.register(r'inventory', StoreInventoryViewSet, basename='store-inventory')
router.register(r'partner-inventory', PartnerInventoryViewSet, basename='partner-inventory')
router.register(r'returns', ReturnRequestViewSet, basename='return-requests')

urlpatterns = [
    path('', include(router.urls)),
]