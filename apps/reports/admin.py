from django.contrib import admin
from django.utils.html import format_html
from .models import Report, SalesReport, InventoryReport


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['name', 'report_type', 'period', 'date_range', 'created_by', 'is_automated', 'created_at']
    list_filter = ['report_type', 'period', 'is_automated', 'created_at']
    search_fields = ['name', 'created_by__name']
    readonly_fields = ['created_at', 'data']

    def date_range(self, obj):
        return f"{obj.date_from} - {obj.date_to}"

    date_range.short_description = 'Период'


@admin.register(SalesReport)
class SalesReportAdmin(admin.ModelAdmin):
    list_display = ['date', 'store', 'product', 'total_revenue', 'profit', 'orders_count']
    list_filter = ['date', 'store']
    search_fields = ['store__store_name', 'product__name']


@admin.register(InventoryReport)
class InventoryReportAdmin(admin.ModelAdmin):
    list_display = ['date', 'store', 'product', 'closing_balance', 'closing_value']
    list_filter = ['date', 'store']