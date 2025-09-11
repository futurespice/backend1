from django.contrib import admin
from .models import Region, DeliveryZone


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'parent', 'region_type', 'is_active', 'created_at']
    list_filter = ['region_type', 'is_active', 'created_at']
    search_fields = ['name', 'code']
    list_editable = ['is_active']
    ordering = ['name']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'code', 'parent', 'region_type')
        }),
        ('GPS координаты', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',)
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('parent')


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ['name', 'region', 'delivery_cost', 'delivery_time_hours', 'is_active']
    list_filter = ['region__region_type', 'is_active']
    search_fields = ['name', 'region__name']
    list_editable = ['delivery_cost', 'is_active']

    fieldsets = (
        ('Основная информация', {
            'fields': ('region', 'name')
        }),
        ('Зона доставки', {
            'fields': ('polygon_coordinates', 'delivery_radius'),
            'description': 'Укажите либо полигон координат, либо радиус доставки'
        }),
        ('Параметры доставки', {
            'fields': ('delivery_cost', 'delivery_time_hours')
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('region')