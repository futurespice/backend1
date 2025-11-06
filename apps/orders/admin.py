from django.contrib import admin
from django.utils.html import format_html
from decimal import Decimal

from .models import (
    PartnerOrder, PartnerOrderItem,
    StoreOrder, StoreOrderItem,
    OrderHistory, OrderReturn, OrderReturnItem
)


# ============= PARTNER ORDERS (партнёр → админ) =============

class PartnerOrderItemInline(admin.TabularInline):
    model = PartnerOrderItem
    extra = 1
    readonly_fields = ['total_display']
    fields = ['product', 'quantity', 'price', 'total_display']

    def total_display(self, obj):
        if obj.price and obj.quantity:
            return f"{obj.total} сом"
        return "—"

    total_display.short_description = 'Итого'


@admin.register(PartnerOrder)
class PartnerOrderAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'partner', 'status', 'total_amount',
        'created_at'
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['partner__name', 'partner__email']
    readonly_fields = ['total_amount', 'idempotency_key', 'created_at', 'updated_at']
    inlines = [PartnerOrderItemInline]

    fieldsets = (
        ('Основная информация', {
            'fields': ('partner', 'status', 'total_amount', 'note')
        }),
        ('Системная информация', {
            'fields': ('idempotency_key', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """N+1 защита"""
        return super().get_queryset(request).select_related('partner')


# ============= STORE ORDERS (магазин → партнёр) =============

class StoreOrderItemInline(admin.TabularInline):
    model = StoreOrderItem
    extra = 1
    readonly_fields = ['total_display']
    fields = ['product', 'quantity', 'price', 'is_bonus', 'total_display']

    def total_display(self, obj):
        if obj.is_bonus:
            return format_html('<span style="color: green;">БОНУС (0 сом)</span>')
        if obj.price and obj.quantity:
            return f"{obj.total} сом"
        return "—"

    total_display.short_description = 'Итого'


@admin.register(StoreOrder)
class StoreOrderAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'store', 'partner', 'is_fulfilled',
        'total_amount', 'bonus_applied', 'created_at'
    ]
    list_filter = ['is_fulfilled', 'created_at']
    search_fields = ['store__name', 'partner__name']
    readonly_fields = ['total_amount', 'bonus_applied', 'idempotency_key', 'created_at', 'updated_at']
    inlines = [StoreOrderItemInline]

    fieldsets = (
        ('Основная информация', {
            'fields': ('store', 'partner', 'store_request', 'is_fulfilled')
        }),
        ('Суммы', {
            'fields': ('total_amount', 'bonus_applied', 'note')
        }),
        ('Системная информация', {
            'fields': ('idempotency_key', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """N+1 защита"""
        return super().get_queryset(request).select_related('store', 'partner', 'store_request')


# ============= ORDER HISTORY =============

@admin.register(OrderHistory)
class OrderHistoryAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'order_type', 'order_id', 'type',
        'product', 'quantity', 'amount', 'created_at'
    ]
    list_filter = ['order_type', 'type', 'created_at']
    search_fields = ['product__name', 'note']
    readonly_fields = ['created_at']

    def get_queryset(self, request):
        """N+1 защита"""
        return super().get_queryset(request).select_related('product')


# ============= ORDER RETURNS =============

class OrderReturnItemInline(admin.TabularInline):
    model = OrderReturnItem
    extra = 1
    readonly_fields = ['total_display']
    fields = ['product', 'quantity', 'price', 'total_display']

    def total_display(self, obj):
        if obj.price and obj.quantity:
            return f"{obj.total} сом"
        return "—"

    total_display.short_description = 'Итого'


@admin.register(OrderReturn)
class OrderReturnAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'order', 'status', 'total_amount',
        'created_at'
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['order__store__name', 'reason']
    readonly_fields = ['total_amount', 'idempotency_key', 'created_at', 'updated_at']
    inlines = [OrderReturnItemInline]

    fieldsets = (
        ('Основная информация', {
            'fields': ('order', 'status', 'total_amount', 'reason')
        }),
        ('Системная информация', {
            'fields': ('idempotency_key', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """N+1 защита"""
        return super().get_queryset(request).select_related('order', 'order__store')