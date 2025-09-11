from django.contrib import admin
from .models import BonusRule, BonusHistory, BonusBalance

@admin.register(BonusRule)
class BonusRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'bonus_type', 'every_nth_free', 'is_active', 'priority']
    list_filter = ['bonus_type', 'is_active', 'applies_to_all_products']
    search_fields = ['name', 'description']
    filter_horizontal = ['products', 'categories', 'stores']
    ordering = ['-priority', 'name']

@admin.register(BonusHistory)
class BonusHistoryAdmin(admin.ModelAdmin):
    list_display = ['store', 'product', 'total_items_purchased', 'bonus_items', 'discount_amount', 'created_at']
    list_filter = ['created_at', 'store']
    search_fields = ['store__store_name', 'product__name']
    readonly_fields = ['created_at']
    ordering = ['-created_at']

@admin.register(BonusBalance)
class BonusBalanceAdmin(admin.ModelAdmin):
    list_display = ['store', 'current_points', 'total_bonus_items_received', 'total_amount_saved', 'last_bonus_date']
    list_filter = ['last_bonus_date']
    search_fields = ['store__store_name']
    readonly_fields = ['updated_at', 'last_bonus_date']