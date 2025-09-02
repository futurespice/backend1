from django.contrib import admin
from .models import Region, City


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('name', 'cities_count', 'created_at')
    search_fields = ('name',)
    ordering = ('name',)

    def cities_count(self, obj):
        return obj.cities.count()

    cities_count.short_description = 'Количество городов'


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name', 'region', 'created_at')
    list_filter = ('region',)
    search_fields = ('name', 'region__name')
    ordering = ('region__name', 'name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('region')