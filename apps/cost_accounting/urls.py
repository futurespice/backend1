from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ExpenseViewSet,
    ProductExpenseViewSet,
    MechanicalExpenseLogViewSet,
    CostSnapshotViewSet,
    RecalculateAPIView,
    BillOfMaterialViewSet,
    BomCostPreviewView,
)

router = DefaultRouter()
router.register(r"expenses", ExpenseViewSet, basename="cost-expense")
router.register(r"product-expenses", ProductExpenseViewSet, basename="cost-product-expense")
router.register(r"mechanical-logs", MechanicalExpenseLogViewSet, basename="cost-mechanical-log")
router.register(r"snapshots", CostSnapshotViewSet, basename="cost-snapshot")
router.register(r"bom", BillOfMaterialViewSet, basename="cost-bom")

urlpatterns = [
    path("", include(router.urls)),
    path("recalculate/", RecalculateAPIView.as_view(), name="cost-recalculate"),
    path("bom/preview-cost/", BomCostPreviewView.as_view(), name="cost-bom-preview"),
]
