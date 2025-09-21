from django.contrib import admin
from .models import Region


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'code', 'is_active', 'priority',
        'delivery_cost', 'delivery_radius_km', 'stores_count'
    ]
    list_filter = ['is_active', 'priority', 'created_at']
    search_fields = ['name', 'code', 'description']
    ordering = ['priority', 'name']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'code', 'description', 'is_active')
        }),
        ('Координаты', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',)
        }),
        ('Настройки доставки', {
            'fields': ('delivery_radius_km', 'delivery_cost', 'priority')
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    def stores_count(self, obj):
        return obj.stores_count

    stores_count.short_description = 'Магазинов'

    actions = ['activate_regions', 'deactivate_regions']

    def activate_regions(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Активировано {updated} регионов')

    activate_regions.short_description = 'Активировать выбранные регионы'

    def deactivate_regions(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано {updated} регионов')

    deactivate_regions.short_description = 'Деактивировать выбранные регионы'

