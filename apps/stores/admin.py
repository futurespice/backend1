from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Region, City, Store, StoreSelection,
    StoreProductRequest, StoreRequest, StoreRequestItem,
    StoreInventory, PartnerInventory, ReturnRequest, ReturnRequestItem
)
from django.db.models import Sum


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'code']
    search_fields = ['name', 'code']
    ordering = ['name']


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'region']
    list_filter = ['region']
    search_fields = ['name', 'region__name']
    ordering = ['region', 'name']


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'name_display', 'inn', 'owner_name', 'phone_display',
        'city_display', 'debt_display', 'approval_status', 'is_active', 'created_at'
    ]
    list_filter = ['approval_status', 'is_active', 'region', 'city', 'created_at']
    search_fields = ['name', 'inn', 'owner_name', 'phone']
    readonly_fields = ['created_by', 'created_at', 'updated_at']
    ordering = ['-created_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'inn', 'owner_name', 'phone')
        }),
        ('Местоположение', {
            'fields': ('region', 'city', 'address', ('latitude', 'longitude'))
        }),
        ('Финансы', {
            'fields': ('debt',)
        }),
        ('Статус', {
            'fields': ('approval_status', 'is_active')
        }),
        ('Системная информация', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def name_display(self, obj):
        return format_html('<strong>{}</strong>', obj.name)

    name_display.short_description = 'Название'

    def phone_display(self, obj):
        return format_html('<span style="color: blue;">{}</span>', obj.phone)

    phone_display.short_description = 'Телефон'

    def city_display(self, obj):
        return f"{obj.city.name} ({obj.region.name})"

    city_display.short_description = 'Город'

    def debt_display(self, obj):
        if obj.debt <= 0:
            return format_html('<span style="color: green;">0 сом</span>')
        elif obj.debt < 10000:
            return format_html('<span style="color: orange;">{} сом</span>', obj.debt)
        return format_html('<span style="color: red;">{} сом</span>', obj.debt)

    debt_display.short_description = 'Долг'

    actions = ['approve_stores', 'reject_stores']

    def approve_stores(self, request, queryset):
        updated = queryset.update(approval_status='approved')
        self.message_user(request, f'Одобрено {updated} магазинов')

    approve_stores.short_description = 'Одобрить выбранные магазины'

    def reject_stores(self, request, queryset):
        updated = queryset.update(approval_status='rejected', is_active=False)
        self.message_user(request, f'Отклонено {updated} магазинов')

    reject_stores.short_description = 'Отклонить выбранные магазины'


class StoreRequestItemInline(admin.TabularInline):
    model = StoreRequestItem
    extra = 1
    readonly_fields = ['total']


@admin.register(StoreSelection)
class StoreSelectionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'store', 'selected_at']
    list_filter = ['selected_at']
    search_fields = ['user__name', 'store__name']
    readonly_fields = ['selected_at']


@admin.register(StoreProductRequest)
class StoreProductRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'store', 'product', 'quantity', 'created_at']
    list_filter = ['created_at']
    search_fields = ['store__name', 'product__name']
    readonly_fields = ['created_at']


@admin.register(StoreRequest)
class StoreRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'store', 'created_by_display', 'total_amount_display',
        'items_count', 'note', 'status', 'created_at'
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['store__name', 'created_by__name', 'note']
    readonly_fields = ['created_by', 'created_at']
    inlines = [StoreRequestItemInline]

    def created_by_display(self, obj):
        if obj.created_by:
            return format_html(
                '<a href="?created_by__id__exact={}">{}</a>',
                obj.created_by.id,
                obj.created_by.phone
            )
        return '—'

    created_by_display.short_description = 'Создал'

    def total_amount_display(self, obj):
        return format_html('<strong>{} сом</strong>', obj.total_amount)

    total_amount_display.short_description = 'Сумма'

    def items_count(self, obj):
        return obj.items.count()

    items_count.short_description = 'Позиций'


@admin.register(StoreInventory)
class StoreInventoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'store', 'product', 'quantity_display', 'total_price_display', 'last_updated']
    list_filter = ['store', 'last_updated']
    search_fields = ['store__name', 'product__name']
    readonly_fields = ['last_updated']
    ordering = ['-last_updated']

    def quantity_display(self, obj):
        if obj.quantity <= 0:
            return format_html('<span style="color: red;">0</span>')
        elif obj.quantity < 10:
            return format_html('<span style="color: orange;">{} {}</span>', obj.quantity,
                               obj.product.get_unit_display())
        return format_html('<span style="color: green;">{} {}</span>', obj.quantity, obj.product.get_unit_display())

    quantity_display.short_description = 'Количество'

    def total_price_display(self, obj):
        return format_html('<strong>{} сом</strong>', obj.total_price)

    total_price_display.short_description = 'Стоимость'


@admin.register(PartnerInventory)
class PartnerInventoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'partner', 'product', 'quantity_display', 'last_updated']
    list_filter = ['partner', 'last_updated']
    search_fields = ['partner__name', 'product__name']
    readonly_fields = ['last_updated']
    ordering = ['-last_updated']

    def quantity_display(self, obj):
        if obj.quantity <= 0:
            return format_html('<span style="color: red;">0</span>')
        return format_html('<span style="color: green;">{} {}</span>', obj.quantity, obj.product.get_unit_display())

    quantity_display.short_description = 'Количество'


class ReturnRequestItemInline(admin.TabularInline):
    model = ReturnRequestItem
    extra = 1
    readonly_fields = ['total']  # Optional, if you have a total property


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'store', 'status', 'total_amount', 'reason', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['store__name', 'reason']
    readonly_fields = ['created_at']
    inlines = [ReturnRequestItemInline]