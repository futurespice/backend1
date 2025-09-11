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
    # Создание заказа
    path('create/', OrderCreateView.as_view(), name='order-create'),

    # Расчёт бонусов
    path('bonus/calculate/', BonusCalculationView.as_view(), name='bonus-calculate'),

    # Роуты ViewSet'ов
    path('', include(router.urls)),
]