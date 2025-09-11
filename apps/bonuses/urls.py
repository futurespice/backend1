from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BonusRuleViewSet, BonusHistoryViewSet,
    BonusCalculationView, BonusAnalyticsView
)

router = DefaultRouter()
router.register(r'rules', BonusRuleViewSet, basename='bonus-rules')
router.register(r'history', BonusHistoryViewSet, basename='bonus-history')

urlpatterns = [
    # Расчёт бонусов
    path('calculate/', BonusCalculationView.as_view(), name='bonus-calculate'),

    # Аналитика бонусов
    path('analytics/', BonusAnalyticsView.as_view(), name='bonus-analytics'),

    # Роуты ViewSet'ов
    path('', include(router.urls)),
]