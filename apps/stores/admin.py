from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Store, StoreInventory, StoreRequest


class StoreInventoryInline(admin.TabularInline):
    """Инлайн для остатков товаров в магазине"""
    model = StoreInventory
    extra = 0
    readonly_fields = ['last_updated']
    fields = ['product', 'quantity', 'reserved_quantity', 'last_updated']


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    """Админка для магазинов"""

    list_display = [
        'store_name', 'user_info', 'region', 'partner_info',
        'total_debt_display', 'orders_count', 'is_active', 'created_at'
    ]
    list_filter = [
        'is_active', 'region', 'partner', 'created_at'
    ]
    search_fields = [
        'store_name', 'address', 'user__name', 'user__email',
        'user__phone', 'partner__name'
    ]
    ordering = ['-created_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'store_name', 'address')
        }),
        ('Локация', {
            'fields': ('region', 'latitude', 'longitude'),
            'description': 'GPS координаты для точного местоположения'
        }),
        ('Партнёр', {
            'fields': ('partner',),
            'description': 'Партнёр, который обслуживает этот магазин'
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
    inlines = [StoreInventoryInline]

    def user_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}<br/>{}</small>',
            obj.user.get_full_name(),
            obj.user.email,
            obj.user.phone
        )

    user_info.short_description = 'Владелец'

    def partner_info(self, obj):
        if obj.partner:
            return format_html(
                '<strong>{}</strong><br/><small>{}</small>',
                obj.partner.get_full_name(),
                obj.partner.phone
            )
        return '-'

    partner_info.short_description = 'Партнёр'

    def total_debt_display(self, obj):
        debt = obj.total_debt
        if debt > 0:
            return format_html('<span style="color: red;">{} сом</span>', debt)
        return '0 сом'

    total_debt_display.short_description = 'Долг'

    # Действия
    actions = ['assign_partner', 'activate_stores', 'deactivate_stores']

    def assign_partner(self, request, queryset):
        # Здесь можно добавить форму для выбора партнёра
        self.message_user(request, 'Для назначения партнёра используйте редактирование магазина.')

    assign_partner.short_description = 'Назначить партнёра'

    def activate_stores(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Активировано {updated} магазинов.')

    activate_stores.short_description = 'Активировать выбранные магазины'

    def deactivate_stores(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано {updated} магазинов.')

    deactivate_stores.short_description = 'Деактивировать выбранные магазины'


@admin.register(StoreInventory)
class StoreInventoryAdmin(admin.ModelAdmin):
    """Админка для остатков товаров в магазинах"""

    list_display = [
        'store', 'product', 'quantity', 'reserved_quantity',
        'available_quantity_display', 'last_updated'
    ]
    list_filter = ['store', 'product__category', 'last_updated']
    search_fields = ['store__store_name', 'product__name']
    ordering = ['-last_updated']

    def available_quantity_display(self, obj):
        available = obj.available_quantity
        if available <= 0:
            return format_html('<span style="color: red;">{}</span>', available)
        elif available < 10:
            return format_html('<span style="color: orange;">{}</span>', available)
        return str(available)

    available_quantity_display.short_description = 'Доступно'

    # Ограничиваем изменения
    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(StoreRequest)
class StoreRequestAdmin(admin.ModelAdmin):
    """Админка для запросов товаров"""

    list_display = [
        'id', 'store', 'partner', 'status_display',
        'total_items', 'total_quantity', 'requested_at'
    ]
    list_filter = ['status', 'requested_at', 'processed_at']
    search_fields = ['store__store_name', 'partner__name']
    ordering = ['-requested_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('store', 'partner', 'status')
        }),
        ('Даты', {
            'fields': ('requested_at', 'processed_at', 'delivered_at')
        }),
        ('Комментарии', {
            'fields': ('store_notes', 'partner_notes'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['requested_at', 'processed_at', 'delivered_at']

    def status_display(self, obj):
        colors = {
            'pending': 'orange',
            'approved': 'green',
            'rejected': 'red',
            'delivered': 'blue',
            'cancelled': 'gray'
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_status_display()
        )

    status_display.short_description = 'Статус'

    # Действия
    actions = ['approve_requests', 'reject_requests']

    def approve_requests(self, request, queryset):
        approved = 0
        for req in queryset.filter(status='pending'):
            req.approve(request.user)
            approved += 1
        self.message_user(request, f'Одобрено {approved} запросов.')

    approve_requests.short_description = 'Одобрить выбранные запросы'

    def reject_requests(self, request, queryset):
        rejected = 0
        for req in queryset.filter(status='pending'):
            req.reject(request.user, 'Отклонено администратором')
            rejected += 1
        self.message_user(request, f'Отклонено {rejected} запросов.')

    reject_requests.short_description = 'Отклонить выбранные запросы'

    # Ограничиваем изменения
    def has_add_permission(self, request):
        return False  # Запросы создаются только через API


