from rest_framework.routers import DefaultRouter
from .views import GeoPingViewSet, GeoDeviceViewSet

router = DefaultRouter()
router.register(r"pings", GeoPingViewSet, basename="geo-pings")
router.register(r"devices", GeoDeviceViewSet, basename="geo-devices")
urlpatterns = router.urls
