from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RegionViewSet, DeliveryZoneViewSet, RegionListView

router = DefaultRouter()
router.register(r'regions', RegionViewSet, basename='regions')
router.register(r'delivery-zones', DeliveryZoneViewSet, basename='delivery-zones')

urlpatterns = [
    # Простой список регионов
    path('list/', RegionListView.as_view(), name='region-list'),

    # Роуты ViewSet'ов
    path('', include(router.urls)),
]