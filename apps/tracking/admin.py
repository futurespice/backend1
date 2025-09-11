from django.contrib import admin
from .models import Vehicle, DeliveryTracking, TrackingPoint

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ['number', 'vehicle_type', 'brand', 'model', 'is_active']
    list_filter = ['vehicle_type', 'is_active']
    search_fields = ['number', 'brand', 'model']
    filter_horizontal = ['drivers']

@admin.register(DeliveryTracking)
class DeliveryTrackingAdmin(admin.ModelAdmin):
    list_display = ['order', 'status', 'vehicle', 'driver', 'updated_at']  # Убрали tracking_number, delivered_at
    list_filter = ['status', 'created_at']
    search_fields = ['order__id', 'notes']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(TrackingPoint)
class TrackingPointAdmin(admin.ModelAdmin):
    list_display = ['tracking', 'latitude', 'longitude', 'timestamp', 'speed_kmh']
    list_filter = ['timestamp']
    readonly_fields = ['timestamp']