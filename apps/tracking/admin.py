from django.contrib import admin
from .models import DeliveryTracking, TrackingEvent, GPSLocation, Vehicle

@admin.register(DeliveryTracking)
class DeliveryTrackingAdmin(admin.ModelAdmin):
    list_display = ['tracking_number', 'status', 'driver', 'created_at', 'delivered_at']
    list_filter = ['status', 'created_at']
    search_fields = ['tracking_number', 'driver__name']

@admin.register(TrackingEvent)
class TrackingEventAdmin(admin.ModelAdmin):
    list_display = ['tracking', 'event_type', 'created_by', 'created_at']
    list_filter = ['event_type', 'created_at']

@admin.register(GPSLocation)
class GPSLocationAdmin(admin.ModelAdmin):
    list_display = ['user', 'latitude', 'longitude', 'created_at']
    list_filter = ['created_at', 'user']

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ['number', 'vehicle_type', 'brand', 'model', 'is_active']
    list_filter = ['vehicle_type', 'is_active']
    filter_horizontal = ['drivers']