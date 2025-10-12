from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, OrderHistoryViewSet, OrderReturnViewSet

router = DefaultRouter()
router.register('orders', OrderViewSet, basename='orders')
router.register('history', OrderHistoryViewSet, basename='history')
router.register('returns', OrderReturnViewSet, basename='returns')

urlpatterns = [
    path('', include(router.urls)),
]