# apps/orders/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OrderViewSet, OrderItemViewSet, ProductRequestViewSet,
    BonusCalculationView, OrderCreateView
)

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='orders')
router.register(r'order-items', OrderItemViewSet, basename='order-items')
router.register(r'product-requests', ProductRequestViewSet, basename='product-requests')

urlpatterns = [
    path('create/', OrderCreateView.as_view(), name='order-create'),
    path('bonus/calculate/', BonusCalculationView.as_view(), name='order-bonus-calculate'),
    path('', include(router.urls)),
]