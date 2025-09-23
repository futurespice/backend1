from django.contrib import admin
from .models import GeoDevice, GeoPing

@admin.register(GeoDevice)
class GeoDeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "device_id", "platform", "last_seen", "is_active")
    search_fields = ("device_id", "user__phone", "user__email")

@admin.register(GeoPing)
class GeoPingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "lat", "lng", "recorded_at", "received_at", "accuracy_m", "is_mock")
    list_filter = ("user", "recorded_at")
    search_fields = ("user__phone", "user__email")
