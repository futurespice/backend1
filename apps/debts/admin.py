from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Debt, DebtPayment, DebtSummary


class DebtPaymentInline(admin.TabularInline):
    model = DebtPayment
    extra = 0
    readonly_fields = ['created_at']
    fields = ['amount', 'payment_method', 'created_at', 'notes']


@admin.register(Debt)
class DebtAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'store_info', 'amount_display', 'remaining_display',
        'status_display', 'overdue_display', 'created_at'
    ]
    list_filter = ['is_paid', 'created_at', 'due_date']
    search_fields = ['store__store_name', 'description', 'notes']
    ordering = ['-created_at']
    inlines = [DebtPaymentInline]

    fieldsets = (
        ('Основная информация', {
            'fields': ('store', 'order', 'amount', 'description')
        }),
        ('Погашение', {
            'fields': ('is_paid', 'paid_amount', 'due_date', 'paid_at')
        }),
        ('Примечания', {
            'fields': ('notes',)
        }),
    )

    readonly_fields = ['paid_at']

    def store_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.store.store_name,
            obj.store.user.get_full_name()
        )

    store_info.short_description = 'Магазин'

    def amount_display(self, obj):
        return f'{obj.amount} сом'

    amount_display.short_description = 'Сумма долга'

    def remaining_display(self, obj):
        remaining = obj.remaining_amount
        if remaining > 0:
            return format_html(
                '<span style="color: red; font-weight: bold;">{} сом</span>',
                remaining
            )
        return '0 сом'

    remaining_display.short_description = 'Остаток'

    def status_display(self, obj):
        if obj.is_paid:
            return format_html('<span style="color: green;">Погашен</span>')
        return format_html('<span style="color: red;">Активен</span>')

    status_display.short_description = 'Статус'

    def overdue_display(self, obj):
        if obj.is_overdue:
            return format_html('<span style="color: red;">Просрочен</span>')
        elif obj.due_date and not obj.is_paid:
            return f'До {obj.due_date}'
        return '-'

    overdue_display.short_description = 'Срок'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'store', 'store__user', 'order'
        )

    # Действия
    actions = ['mark_as_paid']

    def mark_as_paid(self, request, queryset):
        updated = 0
        for debt in queryset.filter(is_paid=False):
            remaining = debt.remaining_amount
            if remaining > 0:
                debt.make_payment(remaining, 'other', 'Отмечен как погашенный через админку')
                updated += 1
        self.message_user(request, f'Помечено как погашенные: {updated} долгов')

    mark_as_paid.short_description = 'Отметить как погашенные'


@admin.register(DebtPayment)
class DebtPaymentAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'debt_info', 'amount_display', 'payment_method',
        'created_at', 'processed_by'
    ]
    list_filter = ['payment_method', 'created_at']
    search_fields = ['debt__store__store_name', 'notes', 'transaction_id']
    ordering = ['-created_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('debt', 'amount', 'payment_method')
        }),
        ('Метаданные', {
            'fields': ('created_at', 'processed_by', 'transaction_id')
        }),
        ('Примечания', {
            'fields': ('notes',)
        }),
    )

    readonly_fields = ['created_at']

    def debt_info(self, obj):
        return format_html(
            'Долг #{}<br/><small>{}</small>',
            obj.debt.id,
            obj.debt.store.store_name
        )

    debt_info.short_description = 'Долг'

    def amount_display(self, obj):
        return f'{obj.amount} сом'

    amount_display.short_description = 'Сумма'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'debt', 'debt__store', 'processed_by'
        )


@admin.register(DebtSummary)
class DebtSummaryAdmin(admin.ModelAdmin):
    list_display = [
        'store_info', 'total_debt_display', 'overdue_debt_display',
        'active_debts_count', 'last_payment_date', 'updated_at'
    ]
    list_filter = ['updated_at', 'last_payment_date']
    search_fields = ['store__store_name']
    ordering = ['-total_debt']

    fieldsets = (
        ('Магазин', {
            'fields': ('store',)
        }),
        ('Суммы долгов', {
            'fields': ('total_debt', 'overdue_debt')
        }),
        ('Счётчики', {
            'fields': ('active_debts_count', 'overdue_debts_count')
        }),
        ('Даты', {
            'fields': ('last_payment_date', 'updated_at')
        }),
    )

    readonly_fields = ['updated_at']

    def store_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.store.store_name,
            obj.store.user.get_full_name()
        )

    store_info.short_description = 'Магазин'

    def total_debt_display(self, obj):
        if obj.total_debt > 0:
            return format_html(
                '<span style="color: red; font-weight: bold;">{} сом</span>',
                obj.total_debt
            )
        return '0 сом'

    total_debt_display.short_description = 'Общий долг'

    def overdue_debt_display(self, obj):
        if obj.overdue_debt > 0:
            return format_html(
                '<span style="color: darkred; font-weight: bold;">{} сом</span>',
                obj.overdue_debt
            )
        return '0 сом'

    overdue_debt_display.short_description = 'Просроченный долг'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('store', 'store__user')

    # Действия
    actions = ['recalculate_summaries']

    def recalculate_summaries(self, request, queryset):
        updated = 0
        for summary in queryset:
            summary.recalculate()
            updated += 1
        self.message_user(request, f'Пересчитано сводок: {updated}')

    recalculate_summaries.short_description = 'Пересчитать сводки'