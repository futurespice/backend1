from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegionViewSet, StoreViewSet, StoreSelectionViewSet,
    StoreProductRequestViewSet, StoreRequestViewSet,
    StoreInventoryViewSet, PartnerInventoryViewSet,
    ReturnRequestViewSet
)

router = DefaultRouter()
router.register('regions', RegionViewSet, basename='regions')
router.register('stores', StoreViewSet, basename='stores')
router.register('selection', StoreSelectionViewSet, basename='selection')
router.register('product-requests', StoreProductRequestViewSet, basename='product-requests')
router.register('requests', StoreRequestViewSet, basename='requests')
router.register('inventory', StoreInventoryViewSet, basename='inventory')
router.register('partner-inventory', PartnerInventoryViewSet, basename='partner-inventory')
router.register('returns', ReturnRequestViewSet, basename='returns')

urlpatterns = [
    path('', include(router.urls)),
]