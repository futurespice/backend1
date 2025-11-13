from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PartnerOrderViewSet, StoreOrderViewSet,
    OrderHistoryViewSet, OrderReturnViewSet
)
from rest_framework.routers import DefaultRouter
from orders import views

router = DefaultRouter()
router.register(r'partner-orders', views.PartnerOrderViewSet)
router.register(r'store-orders', views.StoreOrderViewSet)
router.register(r'order-history', views.OrderHistoryViewSet)
router.register(r'order-returns', views.OrderReturnViewSet)

router = DefaultRouter()
router.register('partner-orders', PartnerOrderViewSet, basename='partner-order')
router.register('store-orders', StoreOrderViewSet, basename='store-order')
router.register('history', OrderHistoryViewSet, basename='order-history')
router.register('returns', OrderReturnViewSet, basename='order-return')

urlpatterns = [
    path('', include(router.urls)),
]