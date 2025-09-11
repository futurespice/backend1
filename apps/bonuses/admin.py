from django.contrib import admin
from django.utils.html import format_html
from .models import BonusRule, BonusHistory


@admin.register(BonusRule)
class BonusRuleAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'every_nth_free', 'applies_to_all_products',
        'products_count', 'is_active', 'date_range'
    ]
    list_filter = ['is_active', 'applies_to_all_products', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['-created_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'description')
        }),
        ('Правила бонусов', {
            'fields': ('every_nth_free',)
        }),
        ('Применимость', {
            'fields': ('applies_to_all_products', 'products')
        }),
        ('Активность', {
            'fields': ('is_active', 'start_date', 'end_date')
        }),
    )

    filter_horizontal = ['products']

    def products_count(self, obj):
        if obj.applies_to_all_products:
            return "Все товары"
        return f"{obj.products.count()} товаров"

    products_count.short_description = 'Товары'

    def date_range(self, obj):
        if obj.start_date and obj.end_date:
            return f"{obj.start_date} - {obj.end_date}"
        elif obj.start_date:
            return f"С {obj.start_date}"
        elif obj.end_date:
            return f"До {obj.end_date}"
        return "Без ограничений"

    date_range.short_description = 'Период действия'


@admin.register(BonusHistory)
class BonusHistoryAdmin(admin.ModelAdmin):
    list_display = [
        'store_info', 'product_name', 'order_info',
        'purchased_quantity', 'bonus_quantity', 'bonus_discount_display',
        'created_at'
    ]
    list_filter = ['created_at', 'product__category']
    search_fields = [
        'store__store_name', 'product__name',
        'order__id', 'store__user__name'
    ]
    ordering = ['-created_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('store', 'product', 'order', 'order_item')
        }),
        ('Количества', {
            'fields': ('purchased_quantity', 'bonus_quantity', 'cumulative_quantity')
        }),
        ('Стоимости', {
            'fields': ('unit_price', 'bonus_discount')
        }),
    )

    readonly_fields = ['created_at']

    def store_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.store.store_name,
            obj.store.user.get_full_name()
        )

    store_info.short_description = 'Магазин'

    def product_name(self, obj):
        return obj.product.name

    product_name.short_description = 'Товар'

    def order_info(self, obj):
        return format_html(
            'Заказ #{}<br/><small>{}</small>',
            obj.order.id,
            obj.order.order_date.strftime('%d.%m.%Y %H:%M')
        )

    order_info.short_description = 'Заказ'

    def bonus_discount_display(self, obj):
        if obj.bonus_discount > 0:
            return format_html(
                '<span style="color: green;">{} сом</span>',
                obj.bonus_discount
            )
        return '0 сом'

    bonus_discount_display.short_description = 'Скидка'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'store', 'store__user', 'product', 'order'
        )

    def has_add_permission(self, request):
        return False  # Записи создаются автоматически

    def has_change_permission(self, request, obj=None):
        return False  # Нельзя изменять историю

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser  # Только суперпользователь может удалять