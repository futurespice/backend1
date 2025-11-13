# from django.urls import path, include
# from rest_framework.routers import DefaultRouter
# from .views import (
#     DebtViewSet, DebtPaymentViewSet, DebtSummaryViewSet,
#     DebtAnalyticsView, PaymentCreateView
# )
#
# router = DefaultRouter()
# router.register(r'debts', DebtViewSet, basename='debts')
# router.register(r'payments', DebtPaymentViewSet, basename='debt-payments')
# router.register(r'summaries', DebtSummaryViewSet, basename='debt-summaries')
#
# urlpatterns = [
#     # Создание платежа
#     path('pay/', PaymentCreateView.as_view(), name='debt-pay'),
#
#     # Аналитика долгов
#     path('analytics/', DebtAnalyticsView.as_view(), name='debt-analytics'),
#
#     # Роуты ViewSet'ов
#     path('', include(router.urls)),
# ]