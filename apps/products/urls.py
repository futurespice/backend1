from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ExpenseViewSet, ProductViewSet, ProductionViewSet,
    BonusViewSet, DefectiveProductViewSet
)

router = DefaultRouter()
router.register('expenses', ExpenseViewSet, basename='expense')
router.register('products', ProductViewSet, basename='product')
router.register('production', ProductionViewSet, basename='production')
router.register('bonuses', BonusViewSet, basename='bonus')
router.register('defects', DefectiveProductViewSet, basename='defect')

urlpatterns = [
    path('', include(router.urls)),
]