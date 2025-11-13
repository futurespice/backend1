# apps/products/admin.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
from django.contrib import admin
from django.utils.html import format_html
from decimal import Decimal
from .models import (
    ProductCategory, Product, ProductImage, Expense, ProductExpenseRelation,
    ProductionRecord, ProductionItem, MechanicalExpenseEntry,
    BonusHistory, StoreProductCounter, DefectiveProduct
)


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'is_active', 'created_at']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at']


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'expense_type', 'status', 'state',
        'price_per_unit_display', 'monthly_amount', 'is_active'
    ]
    list_filter = ['expense_type', 'status', 'state', 'is_active']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']

    def price_per_unit_display(self, obj):
        """Безопасное отображение цены"""
        if obj.price_per_unit:
            return f"{obj.price_per_unit} сом/{obj.unit}"
        return "—"

    price_per_unit_display.short_description = 'Цена за единицу'

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'expense_type', 'status', 'state')
        }),
        ('Физические расходы', {
            'fields': ('price_per_unit', 'unit'),
            'classes': ('collapse',)
        }),
        ('Накладные расходы', {
            'fields': ('monthly_amount', 'apply_type'),
            'classes': ('collapse',)
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    max_num = 3
    fields = ['image', 'position']


class ProductExpenseRelationInline(admin.TabularInline):
    model = ProductExpenseRelation
    extra = 1
    fields = ['expense', 'proportion']
    autocomplete_fields = ['expense']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'category', 'price', 'cost_price', 'is_weight_based',
        'is_active', 'is_available', 'stock_quantity'
    ]
    list_filter = ['category', 'is_weight_based', 'is_active', 'is_available']
    search_fields = ['name', 'description']
    readonly_fields = ['price_per_100g', 'created_at', 'updated_at']
    inlines = [ProductImageInline, ProductExpenseRelationInline]

    fieldsets = (
        ('Основная информация', {
            'fields': ('category', 'name', 'description', 'image')
        }),
        ('Тип товара', {
            'fields': ('unit', 'is_weight_based')
        }),
        ('Цены', {
            'fields': ('price', 'price_per_100g', 'cost_price')
        }),
        ('Запасы', {
            'fields': ('stock_quantity',)
        }),
        ('Статус', {
            'fields': ('is_active', 'is_available')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """N+1 защита"""
        return super().get_queryset(request).select_related('category')


@admin.register(ProductExpenseRelation)
class ProductExpenseRelationAdmin(admin.ModelAdmin):
    list_display = ['product', 'expense', 'proportion']
    search_fields = ['product__name', 'expense__name']
    autocomplete_fields = ['product', 'expense']

    def get_queryset(self, request):
        """N+1 защита"""
        return super().get_queryset(request).select_related('product', 'expense')


class ProductionItemInline(admin.TabularInline):
    model = ProductionItem
    extra = 0
    readonly_fields = [
        'ingredient_cost', 'overhead_cost', 'total_cost',
        'cost_price', 'revenue', 'net_profit'
    ]
    fields = [
        'product', 'quantity_produced', 'suzerain_amount',
        'ingredient_cost', 'overhead_cost', 'total_cost',
        'cost_price', 'revenue', 'net_profit'
    ]


class MechanicalExpenseEntryInline(admin.TabularInline):
    model = MechanicalExpenseEntry
    extra = 1
    fields = ['expense', 'amount_spent']
    autocomplete_fields = ['expense']


@admin.register(ProductionRecord)
class ProductionRecordAdmin(admin.ModelAdmin):
    list_display = ['partner', 'date', 'total_items', 'created_at']
    list_filter = ['date', 'partner']
    search_fields = ['partner__name']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [ProductionItemInline, MechanicalExpenseEntryInline]

    def total_items(self, obj):
        """Количество товаров в записи"""
        return obj.items.count()

    total_items.short_description = 'Товаров'

    def get_queryset(self, request):
        """N+1 защита"""
        return super().get_queryset(request).select_related('partner').prefetch_related('items')


@admin.register(ProductionItem)
class ProductionItemAdmin(admin.ModelAdmin):
    list_display = [
        'record', 'product', 'quantity_produced',
        'cost_price', 'revenue', 'net_profit'
    ]
    readonly_fields = [
        'ingredient_cost', 'overhead_cost', 'total_cost',
        'cost_price', 'revenue', 'net_profit'
    ]
    search_fields = ['product__name']

    def get_queryset(self, request):
        """N+1 защита"""
        return super().get_queryset(request).select_related('record', 'product')


@admin.register(BonusHistory)
class BonusHistoryAdmin(admin.ModelAdmin):
    list_display = ['store', 'partner', 'product', 'quantity', 'bonus_value', 'created_at']
    list_filter = ['created_at']
    search_fields = ['store__name', 'partner__name', 'product__name']
    readonly_fields = ['bonus_value', 'created_at']

    def get_queryset(self, request):
        """N+1 защита"""
        return super().get_queryset(request).select_related('store', 'partner', 'product')


@admin.register(StoreProductCounter)
class StoreProductCounterAdmin(admin.ModelAdmin):
    list_display = [
        'store', 'partner', 'product',
        'total_count', 'product_count',
        'bonus_status', 'last_bonus_at'
    ]
    search_fields = ['store__name', 'partner__name', 'product__name']
    readonly_fields = ['last_bonus_at', 'created_at', 'updated_at']

    def bonus_status(self, obj):
        """Статус бонуса"""
        if obj.check_bonus():
            return format_html('<span style="color: green;">✓ Бонус доступен</span>')
        next_at = 21 - (obj.total_count % 21)
        return format_html(f'Следующий через: {next_at}')

    bonus_status.short_description = 'Статус бонуса'

    def get_queryset(self, request):
        """N+1 защита"""
        return super().get_queryset(request).select_related('store', 'partner', 'product')


@admin.register(DefectiveProduct)
class DefectiveProductAdmin(admin.ModelAdmin):
    list_display = ['product', 'partner', 'quantity', 'status', 'reported_at']
    list_filter = ['status', 'reported_at']
    search_fields = ['product__name', 'partner__name']
    readonly_fields = ['reported_at', 'resolved_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('partner', 'product', 'quantity', 'reason')
        }),
        ('Статус', {
            'fields': ('status', 'reported_at', 'resolved_at')
        }),
    )

    def get_queryset(self, request):
        """N+1 защита"""
        return super().get_queryset(request).select_related('partner', 'product')