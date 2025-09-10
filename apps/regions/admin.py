from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Region, DeliveryZone


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    """Админка для регионов"""

    list_display = [
        'name', 'code', 'region_type', 'parent',
        'stores_count', 'coordinates_display', 'is_active'
    ]
    list_filter = ['region_type', 'is_active', 'parent']
    search_fields = ['name', 'code']
    ordering = ['name']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'code', 'region_type', 'parent')
        }),
        ('Координаты', {
            'fields': ('latitude', 'longitude'),
            'description': 'GPS координаты центра региона'
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    def coordinates_display(self, obj):
        if obj.latitude and obj.longitude:
            return format_html(
                '<a href="https://maps.google.com/?q={},{}" target="_blank">{}, {}</a>',
                obj.latitude, obj.longitude, obj.latitude, obj.longitude
            )
        return '-'

    coordinates_display.short_description = 'Координаты'

    # Действия
    actions = ['activate_regions', 'deactivate_regions']

    def activate_regions(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Активировано {updated} регионов.')

    activate_regions.short_description = 'Активировать выбранные регионы'

    def deactivate_regions(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано {updated} регионов.')

    deactivate_regions.short_description = 'Деактивировать выбранные регионы'


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    """Админка для зон доставки"""

    list_display = [
        'name', 'region', 'delivery_cost', 'delivery_time_hours',
        'delivery_method', 'is_active'
    ]
    list_filter = ['is_active', 'region']
    search_fields = ['name', 'region__name']
    ordering = ['region', 'name']

    fieldsets = (
        ('Основная информация', {
            'fields': ('region', 'name')
        }),
        ('Зона покрытия', {
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

    def delivery_method(self, obj):
        if obj.polygon_coordinates:
            return format_html('<span style="color: blue;">Полигон</span>')
        elif obj.delivery_radius:
            return format_html('<span style="color: green;">Радиус: {} м</span>', obj.delivery_radius)
        return format_html('<span style="color: red;">Не настроено</span>')

    delivery_method.short_description = 'Метод'

    # Действия
    actions = ['activate_zones', 'deactivate_zones']

    def activate_zones(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Активировано {updated} зон доставки.')

    activate_zones.short_description = 'Активировать выбранные зоны'

    def deactivate_zones(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано {updated} зон доставки.')

    deactivate_zones.short_description = 'Деактивировать выбранные зоны'