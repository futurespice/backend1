# apps/orders/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Prefetch
from decimal import Decimal
from typing import Optional

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

    def total_display(self, obj) -> str:
        """Безопасное отображение итоговой суммы позиции"""
        if obj.pk and obj.price is not None and obj.quantity is not None:
            total = obj.total  # Используем @property из модели
            return format_html('<strong>{} сом</strong>', total)
        return "—"

    total_display.short_description = 'Итого'


@admin.register(PartnerOrder)
class PartnerOrderAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'partner_display', 'status', 'total_amount_display',
        'created_at'
    ]
    list_filter = ['status', 'created_at']
    search_fields = [
        'partner__email', 'partner__first_name', 'partner__last_name',
        'partner__username'
    ]
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
        """N+1 защита: подгружаем партнёра и позиции с продуктами"""
        return super().get_queryset(request).select_related('partner').prefetch_related(
            Prefetch('items', queryset=PartnerOrderItem.objects.select_related('product'))
        )

    def partner_display(self, obj) -> str:
        """Безопасное отображение имени партнёра"""
        if not obj.partner:
            return "—"
        return obj.partner.get_full_name() or obj.partner.email or obj.partner.username
    partner_display.short_description = 'Партнёр'
    partner_display.admin_order_field = 'partner__email'

    def total_amount_display(self, obj) -> str:
        """Форматированная сумма"""
        return f"{obj.total_amount} сом" if obj.total_amount else "0 сом"
    total_amount_display.short_description = 'Сумма'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.pk:
            # Пересчитываем total_amount
            total = sum(item.total for item in obj.items.all() if item.price is not None and item.quantity is not None)
            if obj.total_amount != total:
                obj.total_amount = total
                obj.save(update_fields=['total_amount'])


# ============= STORE ORDERS (магазин → партнёр) =============

class StoreOrderItemInline(admin.TabularInline):
    model = StoreOrderItem
    extra = 1
    readonly_fields = ['total_display']
    fields = ['product', 'quantity', 'price', 'is_bonus', 'total_display']

    def total_display(self, obj) -> str:
        """Отображение итога с учётом бонусной позиции"""
        if not obj.pk:
            return "—"
        if obj.is_bonus:
            return format_html('<span style="color: green; font-weight: bold;">БОНУС (0 сом)</span>')
        if obj.price is not None and obj.quantity is not None:
            total = obj.total
            return format_html('<strong>{} сом</strong>', total)
        return "—"

    total_display.short_description = 'Итого'


@admin.register(StoreOrder)
class StoreOrderAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'store', 'partner_display', 'is_fulfilled',
        'total_amount_display', 'bonus_applied_display', 'created_at'
    ]
    list_filter = ['is_fulfilled', 'created_at']
    search_fields = [
        'store__name', 'partner__email', 'partner__first_name', 'partner__last_name'
    ]
    readonly_fields = ['total_amount', 'bonus_applied', 'idempotency_key', 'created_at', 'updated_at']
    inlines = [StoreOrderItemInline]

    fieldsets = (
        ('Основная информация', {
            'fields': ('store', 'partner', 'store_request', 'is_fulfilled')
        }),
        ('Финансы', {
            'fields': ('total_amount', 'bonus_applied', 'note')
        }),
        ('Системная информация', {
            'fields': ('idempotency_key', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """N+1 защита"""
        return super().get_queryset(request).select_related(
            'store', 'partner', 'store_request'
        ).prefetch_related(
            Prefetch('items', queryset=StoreOrderItem.objects.select_related('product'))
        )

    def partner_display(self, obj) -> str:
        if not obj.partner:
            return "—"
        return obj.partner.get_full_name() or obj.partner.email or "Партнёр"
    partner_display.short_description = 'Партнёр'

    def total_amount_display(self, obj) -> str:
        return f"{obj.total_amount} сом" if obj.total_amount else "0 сом"
    total_amount_display.short_description = 'Сумма'

    def bonus_applied_display(self, obj) -> str:
        if obj.bonus_applied and obj.bonus_applied > 0:
            return format_html('<span style="color: green;">{} сом</span>', obj.bonus_applied)
        return "0 сом"
    bonus_applied_display.short_description = 'Бонус'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.pk:
            # Пересчитываем total_amount (без бонусов)
            total = sum(
                item.total for item in obj.items.all()
                if not item.is_bonus and item.price is not None and item.quantity is not None
            )
            bonus = sum(
                item.price * item.quantity for item in obj.items.all()
                if item.is_bonus and item.price is not None and item.quantity is not None
            )
            if obj.total_amount != total or obj.bonus_applied != bonus:
                obj.total_amount = total
                obj.bonus_applied = bonus
                obj.save(update_fields=['total_amount', 'bonus_applied'])


# ============= ORDER HISTORY =============

@admin.register(OrderHistory)
class OrderHistoryAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'order_type', 'order_id', 'type',
        'product_name', 'quantity', 'amount_display', 'created_at'
    ]
    list_filter = ['order_type', 'type', 'created_at']
    search_fields = ['product__name', 'note']
    readonly_fields = ['created_at']

    def get_queryset(self, request):
        """N+1 защита"""
        return super().get_queryset(request).select_related('product')

    def product_name(self, obj) -> str:
        return obj.product.name if obj.product else "—"
    product_name.short_description = 'Товар'
    product_name.admin_order_field = 'product__name'

    def amount_display(self, obj) -> str:
        return f"{obj.amount} сом" if obj.amount else "0 сом"
    amount_display.short_description = 'Сумма'


# ============= ORDER RETURNS =============

class OrderReturnItemInline(admin.TabularInline):
    model = OrderReturnItem
    extra = 1
    readonly_fields = ['total_display']
    fields = ['product', 'quantity', 'price', 'total_display']

    def total_display(self, obj) -> str:
        """Безопасное отображение суммы возврата"""
        if obj.pk and obj.price is not None and obj.quantity is not None:
            total = obj.total
            return format_html('<strong>{} сом</strong>', total)
        return "—"

    total_display.short_description = 'Итого'


@admin.register(OrderReturn)
class OrderReturnAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'order_link', 'status', 'total_amount_display',
        'created_at'
    ]
    list_filter = ['status', 'created_at']
    search_fields = [
        'order__store__name', 'order__partner__email', 'reason'
    ]
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
        return super().get_queryset(request).select_related(
            'order', 'order__store', 'order__partner'
        ).prefetch_related(
            Prefetch('items', queryset=OrderReturnItem.objects.select_related('product'))
        )

    def order_link(self, obj) -> str:
        if not obj.order:
            return "—"
        url = f"/admin/orders/storeorder/{obj.order.id}/change/"
        return format_html('<a href="{}">Заказ #{}</a>', url, obj.order.id)
    order_link.short_description = 'Заказ'
    order_link.admin_order_field = 'order__id'

    def total_amount_display(self, obj) -> str:
        return f"{obj.total_amount} сом" if obj.total_amount else "0 сом"
    total_amount_display.short_description = 'Сумма'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.pk:
            total = sum(
                item.total for item in obj.items.all()
                if item.price is not None and item.quantity is not None
            )
            if obj.total_amount != total:
                obj.total_amount = total
                obj.save(update_fields=['total_amount'])