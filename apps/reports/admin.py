# reports/admin.py
from django.contrib import admin
from django.http import HttpResponse
import csv
from decimal import Decimal

from .models import (
    Report,
    SalesReport,
    InventoryReport,
    DebtReport,
    BonusReport,
    BonusReportMonthly,
    CostReport,
)


# ---------- utility: export selected rows to CSV ----------
def export_as_csv(modeladmin, request, queryset):
    meta = modeladmin.model._meta
    field_names = [f.name for f in meta.fields]

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{meta.model_name}.csv"'
    writer = csv.writer(response)
    writer.writerow(field_names)
    for obj in queryset:
        row = []
        for field in field_names:
            val = getattr(obj, field)
            # приведём Decimal к str, чтобы не терять точность и не получить локаль-зависимый вывод
            if isinstance(val, Decimal):
                val = str(val)
            row.append(val)
        writer.writerow(row)
    return response


export_as_csv.short_description = "Export selected to CSV"


# ---------- base mixins ----------
class ReadonlyTimeMixin:
    readonly_fields = ("created_at", "updated_at")


# ---------- Report ----------
@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "name", "report_type", "period",
        "date_from", "date_to",
        "store", "partner", "product",
        "created_by", "is_automated", "created_at",
    )
    list_filter = (
        "report_type", "period", "is_automated",
        ("created_at", admin.DateFieldListFilter),
        "store", "partner", "product",
    )
    search_fields = (
        "name",
        "store__store_name",
        "partner__username", "partner__email", "partner__first_name", "partner__last_name",
        "product__name",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    autocomplete_fields = ("store", "partner", "product", "created_by")
    actions = [export_as_csv]


# ---------- SalesReport ----------
@admin.register(SalesReport)
class SalesReportAdmin(admin.ModelAdmin):
    list_display = (
        "date", "partner", "store", "product",
        "orders_count", "total_quantity",
        "total_revenue", "total_bonus_discount", "total_cost", "profit",
    )
    list_filter = (
        ("date", admin.DateFieldListFilter),
        "partner", "store", "product",
    )
    search_fields = (
        "product__name",
        "store__store_name",
        "partner__username", "partner__email", "partner__first_name", "partner__last_name",
    )
    date_hierarchy = "date"
    ordering = ("-date",)
    list_select_related = ("partner", "store", "product")
    autocomplete_fields = ("partner", "store", "product")
    actions = [export_as_csv]


# ---------- InventoryReport ----------
@admin.register(InventoryReport)
class InventoryReportAdmin(admin.ModelAdmin):
    list_display = (
        "date", "partner", "store", "product",
        "opening_balance", "received_quantity", "sold_quantity", "closing_balance",
        "opening_value", "closing_value",
        "production_batch",
    )
    list_filter = (
        ("date", admin.DateFieldListFilter),
        "partner", "store", "product",
    )
    search_fields = (
        "product__name",
        "store__store_name",
        "partner__username", "partner__email", "partner__first_name", "partner__last_name",
    )
    date_hierarchy = "date"
    ordering = ("-date",)
    list_select_related = ("partner", "store", "product", "production_batch")
    # autocomplete_fields = ("partner", "store", "product", "production_batch") после того как появится админка в cost_accounting поменять
    autocomplete_fields = ("partner", "store", "product")
    actions = [export_as_csv]


# ---------- DebtReport ----------
@admin.register(DebtReport)
class DebtReportAdmin(admin.ModelAdmin):
    list_display = (
        "date", "partner", "store",
        "opening_debt", "new_debt", "paid_debt", "closing_debt",
    )
    list_filter = (
        ("date", admin.DateFieldListFilter),
        "partner", "store",
    )
    search_fields = (
        "store__store_name",
        "partner__username", "partner__email", "partner__first_name", "partner__last_name",
    )
    date_hierarchy = "date"
    ordering = ("-date",)
    list_select_related = ("partner", "store")
    autocomplete_fields = ("partner", "store")
    actions = [export_as_csv]


# ---------- BonusReport ----------
@admin.register(BonusReport)
class BonusReportAdmin(admin.ModelAdmin):
    list_display = (
        "date", "partner", "store", "product",
        "sold_quantity", "bonus_quantity",
        "bonus_discount", "net_revenue",
        "bonus_rule_n", "production_batch",
    )
    list_filter = (
        ("date", admin.DateFieldListFilter),
        "partner", "store", "product",
        "bonus_rule_n",
    )
    search_fields = (
        "product__name",
        "store__store_name",
        "partner__username", "partner__email", "partner__first_name", "partner__last_name",
    )
    date_hierarchy = "date"
    ordering = ("-date",)
    list_select_related = ("partner", "store", "product", "production_batch")
    # autocomplete_fields = ("partner", "store", "product", "production_batch") после того как появится админка в cost_accounting поменять
    autocomplete_fields = ("partner", "store", "product")
    actions = [export_as_csv]


# ---------- BonusReportMonthly ----------
@admin.register(BonusReportMonthly)
class BonusReportMonthlyAdmin(admin.ModelAdmin):
    list_display = (
        "year", "month", "partner", "store",
        "total_bonus_discount", "total_bonus_items",
        "days_with_bonuses", "avg_daily_bonus_discount", "avg_daily_bonus_items",
    )
    list_filter = ("year", "month", "partner", "store")
    search_fields = (
        "store__store_name",
        "partner__username", "partner__email", "partner__first_name", "partner__last_name",
    )
    ordering = ("-year", "-month")
    list_select_related = ("partner", "store")
    autocomplete_fields = ("partner", "store")
    actions = [export_as_csv]


# ---------- CostReport ----------
@admin.register(CostReport)
class CostReportAdmin(admin.ModelAdmin):
    list_display = (
        "date", "product", "materials_cost", "overhead_cost",
        "total_cost", "produced_quantity", "production_batch",
    )
    list_filter = (
        ("date", admin.DateFieldListFilter),
        "product",
    )
    search_fields = ("product__name",)
    date_hierarchy = "date"
    ordering = ("-date",)
    list_select_related = ("product", "production_batch")
    # autocomplete_fields = ("product", "production_batch")
    autocomplete_fields = ("product",)
    actions = [export_as_csv]
