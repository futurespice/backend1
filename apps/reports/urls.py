from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ReportViewSet,
    SalesReportViewSet, InventoryReportViewSet, DebtReportViewSet,
    BonusReportViewSet, BonusReportMonthlyViewSet, CostReportViewSet,
    WasteLogViewSet, WasteReportViewSet,
)

app_name = "reports"

router = DefaultRouter()
# Журнал отчётов + POST /reports/generate/
router.register(r"report-journal", ReportViewSet, basename="report")

# Витрины
router.register(r"reports/sales", SalesReportViewSet, basename="sales-report")
router.register(r"reports/inventory", InventoryReportViewSet, basename="inventory-report")
router.register(r"reports/debts", DebtReportViewSet, basename="debt-report")
router.register(r"reports/bonuses", BonusReportViewSet, basename="bonus-report")
router.register(r"reports/bonuses-monthly", BonusReportMonthlyViewSet, basename="bonus-report-monthly")
router.register(r"reports/costs", CostReportViewSet, basename="cost-report")

# Брак
router.register(r"reports/waste-logs", WasteLogViewSet, basename="waste-log")
router.register(r"reports/waste", WasteReportViewSet, basename="waste-report")

urlpatterns = [
    path("", include(router.urls)),
]
