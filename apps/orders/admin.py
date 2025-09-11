from django.contrib import admin
from django.utils.html import format_html
from .models import Order, OrderItem, ProductRequest, ProductRequestItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['total_price', 'bonus_discount']
    fields = ['product', 'quantity', 'unit_price', 'total_price', 'bonus_quantity', 'bonus_discount']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'store_info', 'partner_info', 'status_display',
        'total_amount_display', 'debt_amount_display', 'order_date'
    ]
    list_filter = ['status', 'order_date', 'confirmed_date']
    search_fields = ['store__store_name', 'partner__name', 'notes']
    ordering = ['-order_date']
    inlines = [OrderItemInline]

    fieldsets = (
        ('Участники', {
            'fields': ('store', 'partner')
        }),
        ('Статус и даты', {
            'fields': ('status', 'order_date', 'confirmed_date', 'completed_date')
        }),
        ('Суммы', {
            'fields': ('subtotal', 'bonus_discount', 'total_amount', 'payment_amount', 'debt_amount')
        }),
        ('Бонусы', {
            'fields': ('bonus_items_count',)
        }),
        ('Комментарии', {
            'fields': ('notes',)
        }),
    )

    readonly_fields = ['order_date', 'confirmed_date', 'completed_date']

    def store_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.store.store_name,
            obj.store.user.get_full_name()
        )

    store_info.short_description = 'Магазин'

    def partner_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.partner.get_full_name(),
            obj.partner.phone
        )

    partner_info.short_description = 'Партнёр'

    def status_display(self, obj):
        colors = {
            'pending': 'orange',
            'confirmed': 'blue',
            'completed': 'green',
            'cancelled': 'red'
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_status_display()
        )

    status_display.short_description = 'Статус'

    def total_amount_display(self, obj):
        return f'{obj.total_amount} сом'

    total_amount_display.short_description = 'Сумма'

    def debt_amount_display(self, obj):
        if obj.debt_amount > 0:
            return format_html(
                '<span style="color: red;">{} сом</span>',
                obj.debt_amount
            )
        return '0 сом'

    debt_amount_display.short_description = 'Долг'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'store', 'store__user', 'partner'
        )

    # Действия
    actions = ['confirm_orders', 'complete_orders']

    def confirm_orders(self, request, queryset):
        updated = 0
        for order in queryset.filter(status='pending'):
            order.confirm()
            updated += 1
        self.message_user(request, f'Подтверждено заказов: {updated}')

    confirm_orders.short_description = 'Подтвердить выбранные заказы'

    def complete_orders(self, request, queryset):
        updated = 0
        for order in queryset.filter(status='confirmed'):
            order.complete()
            updated += 1
        self.message_user(request, f'Завершено заказов: {updated}')

    complete_orders.short_description = 'Завершить выбранные заказы'


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = [
        'order', 'product', 'quantity', 'unit_price',
        'total_price', 'bonus_quantity', 'bonus_discount'
    ]
    list_filter = ['order__status', 'product__category']
    search_fields = ['order__id', 'product__name']
    ordering = ['-order__order_date']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'order', 'order__store', 'product'
        )


class ProductRequestItemInline(admin.TabularInline):
    model = ProductRequestItem
    extra = 0
    fields = ['product', 'requested_quantity']


@admin.register(ProductRequest)
class ProductRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'partner_info', 'status_display', 'total_items',
        'requested_at', 'processed_at'
    ]
    list_filter = ['status', 'requested_at']
    search_fields = ['partner__name', 'partner_notes']
    ordering = ['-requested_at']
    inlines = [ProductRequestItemInline]

    fieldsets = (
        ('Основная информация', {
            'fields': ('partner', 'status')
        }),
        ('Даты', {
            'fields': ('requested_at', 'processed_at')
        }),
        ('Комментарии', {
            'fields': ('partner_notes', 'admin_notes')
        }),
    )

    readonly_fields = ['requested_at', 'processed_at']

    def partner_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.partner.get_full_name(),
            obj.partner.phone
        )

    partner_info.short_description = 'Партнёр'

    def status_display(self, obj):
        colors = {
            'pending': 'orange',
            'approved': 'green',
            'rejected': 'red',
            'cancelled': 'gray'
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_status_display()
        )

    status_display.short_description = 'Статус'

    def total_items(self, obj):
        return obj.items.count()

    total_items.short_description = 'Позиций'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('partner')

    # Действия
    actions = ['approve_requests', 'reject_requests']

    def approve_requests(self, request, queryset):
        updated = 0
        for req in queryset.filter(status='pending'):
            req.approve(request.user)
            updated += 1
        self.message_user(request, f'Одобрено запросов: {updated}')

    approve_requests.short_description = 'Одобрить выбранные запросы'

    def reject_requests(self, request, queryset):
        updated = 0
        for req in queryset.filter(status='pending'):
            req.reject(request.user)
            updated += 1
        self.message_user(request, f'Отклонено запросов: {updated}')

    reject_requests.short_description = 'Отклонить выбранные запросы'