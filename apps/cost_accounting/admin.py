from django.contrib import admin
from django.db.models import Sum, Count

from .models import (
    Expense, ProductExpense, BillOfMaterial, BOMLine,
    DailyExpenseLog, ProductionBatch, MonthlyOverheadBudget
)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'type', 'status', 'state',
        'unit', 'price_per_unit', 'is_universal', 'is_active'
    ]
    list_filter = ['type', 'status', 'state', 'is_universal', 'is_active']
    search_fields = ['name']
    ordering = ['type', 'name']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'type')
        }),
        ('Характеристики (только для физических)', {
            'fields': ('unit', 'price_per_unit'),
        }),
        ('Поведение', {
            'fields': ('status', 'state', 'is_universal', 'is_active')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ['created_at', 'updated_at']

    actions = ['make_active', 'make_inactive', 'make_universal']

    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} расходов активированы.')

    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} расходов деактивированы.')

    def make_universal(self, request, queryset):
        updated = queryset.update(is_universal=True)
        self.message_user(request, f'{updated} расходов сделаны универсальными.')

    make_active.short_description = "Активировать выбранные расходы"
    make_inactive.short_description = "Деактивировать выбранные расходы"
    make_universal.short_description = "Сделать универсальными"


class BOMLineInline(admin.TabularInline):
    model = BOMLine
    extra = 1
    fields = ['expense', 'component_product', 'quantity', 'unit', 'is_primary', 'order']


@admin.register(BillOfMaterial)
class BillOfMaterialAdmin(admin.ModelAdmin):
    list_display = ['product', 'version', 'components_count', 'has_primary', 'is_active']
    list_filter = ['is_active', 'version']
    search_fields = ['product__name']
    inlines = [BOMLineInline]

    readonly_fields = ['created_at', 'updated_at']

    @admin.display(description='Компонентов')
    def components_count(self, obj):
        return obj.lines.count()

    @admin.display(description='Есть Сюзерен', boolean=True)
    def has_primary(self, obj):
        return obj.lines.filter(is_primary=True).exists()


@admin.register(ProductExpense)
class ProductExpenseAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'expense', 'expense_type', 'ratio_per_product_unit',
        'is_active'
    ]
    list_filter = ['expense__type', 'expense__status', 'is_active']
    search_fields = ['product__name', 'expense__name']

    @admin.display(description='Тип расхода', ordering='expense__type')
    def expense_type(self, obj):
        return obj.expense.get_type_display()


@admin.register(DailyExpenseLog)
class DailyExpenseLogAdmin(admin.ModelAdmin):
    list_display = [
        'expense', 'date', 'expense_type', 'quantity_used',
        'actual_price_per_unit', 'daily_amount', 'total_cost'
    ]
    list_filter = ['date', 'expense__type']
    search_fields = ['expense__name']
    date_hierarchy = 'date'
    ordering = ['-date', 'expense__name']

    readonly_fields = ['total_cost', 'created_at', 'updated_at']

    @admin.display(description='Тип', ordering='expense__type')
    def expense_type(self, obj):
        return obj.expense.get_type_display()


@admin.register(ProductionBatch)
class ProductionBatchAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'date', 'produced_quantity', 'cost_per_unit',
        'total_cost', 'revenue', 'net_profit'
    ]
    list_filter = ['date', 'product__category_type']
    search_fields = ['product__name']
    date_hierarchy = 'date'
    ordering = ['-date', 'product__name']

    readonly_fields = [
        'physical_cost', 'overhead_cost', 'total_cost', 'cost_per_unit',
        'net_profit', 'created_at', 'updated_at'
    ]


@admin.register(MonthlyOverheadBudget)
class MonthlyOverheadBudgetAdmin(admin.ModelAdmin):
    list_display = [
        'expense', 'year', 'month', 'planned_amount', 'actual_amount'
    ]
    list_filter = ['year', 'month']
    search_fields = ['expense__name']
    ordering = ['-year', '-month', 'expense__name']

    readonly_fields = ['actual_amount', 'created_at', 'updated_at']


# Простая аналитика
class CostAnalyticsAdmin(admin.ModelAdmin):
    """Простая аналитика себестоимости"""

    def changelist_view(self, request, extra_context=None):
        from datetime import date, timedelta

        # Статистика за последние 30 дней
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        recent_batches = ProductionBatch.objects.filter(
            date__range=[start_date, end_date]
        )

        total_batches = recent_batches.count()
        total_costs = recent_batches.aggregate(total=Sum('total_cost'))['total'] or 0
        total_revenue = recent_batches.aggregate(total=Sum('revenue'))['total'] or 0

        # Активные расходы
        active_expenses = Expense.objects.filter(is_active=True).count()
        physical_expenses = Expense.objects.filter(is_active=True, type='physical').count()
        overhead_expenses = Expense.objects.filter(is_active=True, type='overhead').count()

        extra_context = extra_context or {}
        extra_context.update({
            'period_days': 30,
            'total_batches': total_batches,
            'total_costs': total_costs,
            'total_revenue': total_revenue,
            'active_expenses': active_expenses,
            'physical_expenses': physical_expenses,
            'overhead_expenses': overhead_expenses,
            'title': 'Аналитика себестоимости',
        })

        return super().changelist_view(request, extra_context)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Прокси для аналитики
class AnalyticsProxy(ProductionBatch):
    class Meta:
        proxy = True
        verbose_name = "Аналитика себестоимости"
        verbose_name_plural = "Аналитика себестоимости"


admin.site.register(AnalyticsProxy, CostAnalyticsAdmin)

# Настройки админки
admin.site.site_header = "БайЭл - Управление себестоимостью"
admin.site.site_title = "БайЭл Админ"
admin.site.index_title = "Система расчета себестоимости"