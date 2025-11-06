from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PartnerOrderViewSet, StoreOrderViewSet,
    OrderHistoryViewSet, OrderReturnViewSet
)

router = DefaultRouter()
router.register('partner-orders', PartnerOrderViewSet, basename='partner-order')
router.register('store-orders', StoreOrderViewSet, basename='store-order')
router.register('history', OrderHistoryViewSet, basename='order-history')
router.register('returns', OrderReturnViewSet, basename='order-return')

urlpatterns = [
    path('', include(router.urls)),
]