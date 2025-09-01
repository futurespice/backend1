from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'regions', views.RegionViewSet)
router.register(r'cities', views.CityViewSet)

urlpatterns = [
    path('', include(router.urls)),
]