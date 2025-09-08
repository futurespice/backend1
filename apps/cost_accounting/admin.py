# cost_accounting/admin.py
from django.contrib import admin, messages
from django.db.models import Sum, Count, Q, Avg
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import (
    Expense, ProductExpense, DailyExpenseLog,
    ProductionBatch, MonthlyOverheadBudget,
    BillOfMaterial, BOMLine
)


# ---------- Inlines ----------
class BOMLineInline(admin.TabularInline):
    model = BOMLine
    extra = 1
    fields = ['expense', 'component_product', 'quantity', 'unit', 'is_primary', 'order']
    autocomplete_fields = ['expense', 'component_product']
    ordering = ['order', 'is_primary']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('expense', 'component_product')


# ---------- Custom Filters ----------
class ExpenseTypeFilter(admin.SimpleListFilter):
    title = 'Тип расхода'
    parameter_name = 'type'

    def lookups(self, request, model_admin):
        return Expense.ExpenseType.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(type=self.value())
        return queryset


class ExpenseStatusFilter(admin.SimpleListFilter):
    title = 'Статус расхода'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return Expense.ExpenseStatus.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


class ProductionPeriodFilter(admin.SimpleListFilter):
    title = 'Период производства'
    parameter_name = 'production_period'

    def lookups(self, request, model_admin):
        return (
            ('today', 'Сегодня'),
            ('week', 'Эта неделя'),
            ('month', 'Этот месяц'),
        )

    def queryset(self, request, queryset):
        from datetime import date, timedelta

        if self.value() == 'today':
            return queryset.filter(date=date.today())
        elif self.value() == 'week':
            start_date = date.today() - timedelta(days=7)
            return queryset.filter(date__gte=start_date)
        elif self.value() == 'month':
            start_date = date.today().replace(day=1)
            return queryset.filter(date__gte=start_date)
        return queryset


# ---------- Main Admin Classes ----------
@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'type', 'status', 'price_per_unit', 'unit',
        'products_using_count', 'is_universal', 'is_active'
    ]
    list_filter = [ExpenseTypeFilter, ExpenseStatusFilter, 'is_active', 'is_universal']
    search_fields = ['name', 'description']
    ordering = ['type', 'name']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'description', 'type', 'status')
        }),
        ('Цена и единицы', {
            'fields': ('price_per_unit', 'unit')
        }),
        ('Настройки', {
            'fields': ('is_active', 'is_universal')
        }),
        ('Системные поля', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _products_using_count=Count('product_expenses', filter=Q(product_expenses__is_active=True))
        )

    @admin.display(description='Товаров использует', ordering='_products_using_count')
    def products_using_count(self, obj):
        count = obj._products_using_count
        if count > 0:
            url = reverse('admin:cost_accounting_productexpense_changelist')
            return format_html(
                '<a href="{}?expense__id__exact={}">{}</a>',
                url, obj.id, count
            )
        return '0'

    actions = ['make_active', 'make_inactive', 'make_universal']

    @admin.action(description="Активировать выбранные расходы")
    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} расходов активированы.')

    @admin.action(description="Деактивировать выбранные расходы")
    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} расходов деактивированы.')

    @admin.action(description="Сделать универсальными")
    def make_universal(self, request, queryset):
        updated = queryset.update(is_universal=True)
        self.message_user(request, f'{updated} расходов сделаны универсальными.')


@admin.register(BillOfMaterial)
class BillOfMaterialAdmin(admin.ModelAdmin):
    list_display = ['product', 'version', 'components_count', 'has_primary', 'is_active', 'created_at']
    list_filter = ['is_active', 'version', 'created_at']
    search_fields = ['product__name']
    inlines = [BOMLineInline]
    autocomplete_fields = ['product']

    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Основное', {
            'fields': ('product', 'version', 'is_active')
        }),
        ('Системные поля', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product').prefetch_related('lines')

    @admin.display(description='Компонентов')
    def components_count(self, obj):
        return obj.lines.count()

    @admin.display(description='Есть Сюзерен', boolean=True)
    def has_primary(self, obj):
        return obj.lines.filter(is_primary=True).exists()

    def save_formset(self, request, form, formset, change):
        """Проверяем, что есть только один Сюзерен"""
        if formset.model == BOMLine:
            instances = formset.save(commit=False)
            primary_count = sum(1 for instance in instances if instance.is_primary)

            # Добавляем существующие primary
            existing_primary = BOMLine.objects.filter(
                bom=form.instance,
                is_primary=True
            ).exclude(id__in=[instance.id for instance in instances if instance.id])

            if primary_count + existing_primary.count() > 1:
                messages.warning(request, 'Может быть только один компонент-Сюзерен!')

        super().save_formset(request, form, formset, change)


@admin.register(ProductExpense)
class ProductExpenseAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'expense', 'expense_type', 'expense_status',
        'ratio_per_product_unit', 'is_active'
    ]
    list_filter = ['expense__type', 'expense__status', 'is_active', 'product__category']
    search_fields = ['product__name', 'expense__name']
    autocomplete_fields = ['product', 'expense']

    fieldsets = (
        ('Связь', {
            'fields': ('product', 'expense')
        }),
        ('Параметры', {
            'fields': ('ratio_per_product_unit', 'is_active')
        }),
        ('Системные поля', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    # ИСПРАВЛЕНО: убрано updated_at, которого нет в модели
    readonly_fields = ['created_at']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'expense')

    @admin.display(description='Тип расхода', ordering='expense__type')
    def expense_type(self, obj):
        return obj.expense.get_type_display()

    @admin.display(description='Статус расхода', ordering='expense__status')
    def expense_status(self, obj):
        status = obj.expense.get_status_display()
        if obj.expense.status == Expense.ExpenseStatus.SUZERAIN:
            return format_html('<strong style="color: #e74c3c;">{}</strong>', status)
        return status


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
    autocomplete_fields = ['expense']

    readonly_fields = ['total_cost', 'created_at', 'updated_at']

    fieldsets = (
        ('Основное', {
            'fields': ('expense', 'date')
        }),
        ('Количество и цены', {
            'fields': ('quantity_used', 'actual_price_per_unit', 'daily_amount')
        }),
        ('Расчетные поля', {
            'fields': ('total_cost',),
            'classes': ('collapse',)
        }),
        ('Системные поля', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('expense')

    @admin.display(description='Тип', ordering='expense__type')
    def expense_type(self, obj):
        return obj.expense.get_type_display()

    def save_model(self, request, obj, form, change):
        """Автоматически рассчитываем total_cost"""
        if obj.quantity_used and obj.actual_price_per_unit:
            obj.total_cost = obj.quantity_used * obj.actual_price_per_unit
        super().save_model(request, obj, form, change)


@admin.register(ProductionBatch)
class ProductionBatchAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'date', 'produced_quantity', 'cost_per_unit',
        'total_cost', 'revenue', 'net_profit', 'profitability_display'
    ]
    list_filter = [ProductionPeriodFilter, 'product__category']
    search_fields = ['product__name']
    date_hierarchy = 'date'
    ordering = ['-date', 'product__name']
    autocomplete_fields = ['product']

    readonly_fields = [
        'physical_cost', 'overhead_cost', 'total_cost', 'cost_per_unit',
        'net_profit', 'cost_breakdown_display', 'created_at', 'updated_at'
    ]

    fieldsets = (
        ('Производство', {
            'fields': ('product', 'date', 'produced_quantity', 'suzerain_input_amount')
        }),
        ('Себестоимость', {
            'fields': ('physical_cost', 'overhead_cost', 'total_cost', 'cost_per_unit'),
            'classes': ('collapse',)
        }),
        ('Продажи и прибыль', {
            'fields': ('revenue', 'net_profit')
        }),
        ('Детализация', {
            'fields': ('cost_breakdown_display',),
            'classes': ('collapse',)
        }),
        ('Системные поля', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')

    @admin.display(description='Рентабельность')
    def profitability_display(self, obj):
        if obj.revenue > 0:
            margin = (obj.net_profit / obj.revenue) * 100
            color = '#27ae60' if margin > 10 else '#f39c12' if margin > 0 else '#e74c3c'
            return format_html(
                '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
                color, margin
            )
        return '—'

    @admin.display(description='Детализация расходов')
    def cost_breakdown_display(self, obj):
        if not obj.cost_breakdown:
            return 'Нет данных'

        html = '<div style="max-height: 300px; overflow-y: auto;">'

        # Физические расходы
        physical = obj.cost_breakdown.get('physical_costs', [])
        if physical:
            html += '<h4>Физические расходы:</h4><ul>'
            for item in physical:
                html += f'<li>{item["name"]}: {item["consumed_quantity"]} {item["unit"]} × {item["unit_price"]} = {item["total_cost"]} сом</li>'
            html += '</ul>'

        # Компоненты-продукты
        components = obj.cost_breakdown.get('component_costs', [])
        if components:
            html += '<h4>Компоненты-продукты:</h4><ul>'
            for item in components:
                html += f'<li>{item["name"]}: {item["consumed_quantity"]} {item["unit"]} × {item["unit_price"]} = {item["total_cost"]} сом</li>'
            html += '</ul>'

        # Накладные расходы
        overhead = obj.cost_breakdown.get('overhead_costs', [])
        if overhead:
            html += '<h4>Накладные расходы:</h4><ul>'
            for item in overhead:
                html += f'<li>{item["name"]}: {item["allocated_cost"]} сом (доля: {item["product_share"]:.1%})</li>'
            html += '</ul>'

        html += '</div>'
        return mark_safe(html)


@admin.register(MonthlyOverheadBudget)
class MonthlyOverheadBudgetAdmin(admin.ModelAdmin):
    list_display = [
        'expense', 'year', 'month', 'planned_amount', 'actual_amount', 'variance_display'
    ]
    list_filter = ['year', 'month', 'expense__type']
    search_fields = ['expense__name']
    ordering = ['-year', '-month', 'expense__name']
    autocomplete_fields = ['expense']

    readonly_fields = ['actual_amount', 'created_at', 'updated_at']

    fieldsets = (
        ('Период', {
            'fields': ('year', 'month', 'expense')
        }),
        ('Бюджет', {
            'fields': ('planned_amount', 'actual_amount')
        }),
        ('Системные поля', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('expense')

    @admin.display(description='Отклонение')
    def variance_display(self, obj):
        if obj.actual_amount and obj.planned_amount:
            variance = obj.actual_amount - obj.planned_amount
            percent = (variance / obj.planned_amount) * 100
            color = '#e74c3c' if variance > 0 else '#27ae60'
            return format_html(
                '<span style="color: {};">{:+.0f} ({:+.1f}%)</span>',
                color, variance, percent
            )
        return '—'


# ---------- Analytics Admin ----------
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
        avg_profitability = recent_batches.aggregate(
            avg_margin=Avg('net_profit')
        )['avg_margin'] or 0

        # Активные расходы
        active_expenses = Expense.objects.filter(is_active=True).count()
        physical_expenses = Expense.objects.filter(is_active=True, type='physical').count()
        overhead_expenses = Expense.objects.filter(is_active=True, type='overhead').count()

        # Топ-5 самых дорогих товаров по себестоимости
        top_expensive = ProductionBatch.objects.filter(
            date__range=[start_date, end_date]
        ).order_by('-cost_per_unit')[:5]

        # Топ-5 самых прибыльных товаров
        top_profitable = recent_batches.filter(
            revenue__gt=0
        ).extra(
            select={'profit_margin': 'net_profit / revenue * 100'}
        ).order_by('-profit_margin')[:5]

        extra_context = extra_context or {}
        extra_context.update({
            'period_days': 30,
            'total_batches': total_batches,
            'total_costs': total_costs,
            'total_revenue': total_revenue,
            'avg_profitability': avg_profitability,
            'active_expenses': active_expenses,
            'physical_expenses': physical_expenses,
            'overhead_expenses': overhead_expenses,
            'top_expensive': top_expensive,
            'top_profitable': top_profitable,
            'title': 'Аналитика себестоимости',
        })

        return super().changelist_view(request, extra_context)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Прокси модель для аналитики
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