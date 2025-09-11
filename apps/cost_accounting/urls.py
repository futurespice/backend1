# apps/cost_accounting/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()

# Основные ViewSets
router.register(r'expenses', views.ExpenseViewSet)
router.register(r'product-expenses', views.ProductExpenseViewSet, basename='cost-product-expenses')  # изменили basename
router.register(r'daily-logs', views.DailyExpenseLogViewSet)
router.register(r'production-batches', views.ProductionBatchViewSet)
router.register(r'monthly-budgets', views.MonthlyOverheadBudgetViewSet)
router.register(r'bom', views.BOMViewSet, basename='bom')

# Аналитика
router.register(r'analytics', views.CostAnalyticsViewSet, basename='cost-analytics')

app_name = 'cost_accounting'

urlpatterns = [
    path('', include(router.urls)),

    # Дополнительные endpoints
    path('quick-setup/', views.QuickSetupView.as_view(), name='quick-setup'),
    path('calculate-batch-cost/', views.BatchCostCalculationView.as_view(), name='batch-cost'),
# apps/cost_accounting/urls.py
    path('bonus/', include([
    path('calculate/', views.CostBonusCalculationView.as_view(), name='cost-bonus-calculate'),  # переименовали
    path('analyze/', views.BonusAnalysisView.as_view(), name='bonus-analyze'),
])),
]