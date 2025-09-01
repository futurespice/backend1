from django.contrib import admin
from .models import Store


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('name', 'inn', 'owner', 'user', 'full_address', 'phone', 'is_active', 'debt_amount', 'created_at')
    list_filter = ('is_active', 'region', 'city', 'owner')
    search_fields = ('name', 'inn', 'phone', 'contact_name', 'owner__email', 'user__email')
    ordering = ('-created_at',)

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'inn', 'phone', 'contact_name')
        }),
        ('Владельцы', {
            'fields': ('owner', 'user')
        }),
        ('Местоположение', {
            'fields': ('region', 'city', 'address')
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'owner', 'user', 'region', 'city'
        )

    def debt_amount(self, obj):
        debt = obj.get_debt_amount()
        if debt > 0:
            return f"{debt} сом"
        return "Нет долга"

    debt_amount.short_description = "Долг"

    actions = ['activate_stores', 'deactivate_stores']

    def activate_stores(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} магазинов активировано.')

    activate_stores.short_description = "Активировать выбранные магазины"

    def deactivate_stores(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} магазинов деактивировано.')

    deactivate_stores.short_description = "Деактивировать выбранные магазины"