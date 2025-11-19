# apps/orders/urls.py

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    OrderHistoryViewSet,
    OrderReturnViewSet,
    PartnerOrderViewSet,
    StoreOrderViewSet,
)

router = DefaultRouter()
router.register("partner-orders", PartnerOrderViewSet, basename="partner-order")
router.register("store-orders", StoreOrderViewSet, basename="store-order")
router.register("order-returns", OrderReturnViewSet, basename="order-return")
router.register("order-history", OrderHistoryViewSet, basename="order-history")

urlpatterns = [
    path("", include(router.urls)),
]
