# apps/messaging/urls.py

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ChatThreadViewSet

router = DefaultRouter()
router.register("threads", ChatThreadViewSet, basename="chat-thread")

urlpatterns = [
    path("", include(router.urls)),
]
