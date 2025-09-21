from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RegionViewSet

router = DefaultRouter()
router.register(r'regions', RegionViewSet)

app_name = 'regions'

urlpatterns = [
    path('', include(router.urls)),
]