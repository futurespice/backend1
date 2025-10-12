from django.contrib import admin
from .models import (
    Expense, Product, ProductImage, ProductExpenseRelation,
    ProductionRecord, ProductionItem, MechanicalExpenseEntry,
    BonusHistory, StoreProductCounter, DefectiveProduct
)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['name', 'expense_type', 'status', 'state', 'price_per_unit', 'monthly_amount', 'is_active']
    list_filter = ['expense_type', 'status', 'state', 'is_active']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']

    def get_readonly_fields(self, request, obj=None):
        """Если статус Сюзерен — он не меняется автоматически"""
        if obj and obj.status == 'suzerain':
            return self.readonly_fields
        return self.readonly_fields


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    max_num = 3


class ProductExpenseRelationInline(admin.TabularInline):
    model = ProductExpenseRelation
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'is_bonus', 'is_active', 'position']
    list_filter = ['category', 'is_bonus', 'is_active']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [ProductImageInline, ProductExpenseRelationInline]


@admin.register(ProductExpenseRelation)
class ProductExpenseRelationAdmin(admin.ModelAdmin):
    list_display = ['product', 'expense', 'proportion']
    search_fields = ['product__name', 'expense__name']


class ProductionItemInline(admin.TabularInline):
    model = ProductionItem
    extra = 0
    readonly_fields = ['ingredient_cost', 'overhead_cost', 'total_cost', 'cost_price', 'revenue', 'net_profit']


class MechanicalExpenseEntryInline(admin.TabularInline):
    model = MechanicalExpenseEntry
    extra = 1


@admin.register(ProductionRecord)
class ProductionRecordAdmin(admin.ModelAdmin):
    list_display = ['date', 'created_at']
    list_filter = ['date']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [ProductionItemInline, MechanicalExpenseEntryInline]


@admin.register(ProductionItem)
class ProductionItemAdmin(admin.ModelAdmin):
    list_display = ['record', 'product', 'quantity_produced', 'cost_price', 'net_profit']
    readonly_fields = ['ingredient_cost', 'overhead_cost', 'total_cost', 'cost_price', 'revenue', 'net_profit']


@admin.register(BonusHistory)
class BonusHistoryAdmin(admin.ModelAdmin):
    list_display = ['partner', 'store', 'product', 'bonus_count', 'date']
    list_filter = ['date']
    search_fields = ['partner__username', 'store__username', 'product__name']


@admin.register(StoreProductCounter)
class StoreProductCounterAdmin(admin.ModelAdmin):
    list_display = ['store', 'partner', 'product', 'total_count', 'bonus_eligible_count']
    search_fields = ['store__username', 'partner__username', 'product__name']


@admin.register(DefectiveProduct)
class DefectiveProductAdmin(admin.ModelAdmin):
    list_display = ['product', 'partner', 'quantity', 'amount', 'date']
    list_filter = ['date']
    search_fields = ['product__name', 'partner__username']
    readonly_fields = ['created_at']