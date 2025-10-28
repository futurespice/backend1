# apps/orders/admin.py
from decimal import Decimal
from django.contrib import admin
from django.db import transaction
from django.utils.html import format_html

from .models import Order, OrderItem, OrderReturn, OrderReturnItem


# ---------- Inlines ----------

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product", "quantity", "price", "line_total")
    readonly_fields = ("line_total",)

    @staticmethod
    def line_total(obj):
        if obj.quantity is None or obj.price is None:
            return "-"
        return f"{(obj.quantity * obj.price):.2f}"


class OrderReturnItemInline(admin.TabularInline):
    model = OrderReturnItem
    extra = 0
    fields = ("product", "quantity", "price", "line_total")
    readonly_fields = ("line_total",)

    @staticmethod
    def line_total(obj):
        if obj.quantity is None or obj.price is None:
            return "-"
        return f"{(obj.quantity * obj.price):.2f}"


# ---------- Admin: Order ----------

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "store",
        "partner",
        "status_badge",
        "total_amount_display",
        "debt_increase_display",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("store__name", "partner__username", "note")
    ordering = ("-created_at",)
    inlines = [OrderItemInline]
    readonly_fields = ('idempotency_key', 'created_at', 'updated_at')

    fieldsets = (
        ("Участники", {"fields": ("store", "partner")}),
        ("Статус", {"fields": ("status",)}),
        ("Суммы", {"fields": ("total_amount", "debt_increase")}),
        ("Комментарии", {"fields": ("note",)}),
        ("Системные поля", {"fields": ("created_at",)}),
    )

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        # НЕ вызываем сервисы, просто сохраняем
        super().save_model(request, obj, form, change)

    @transaction.atomic
    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for inst in instances:
            inst.save()
        formset.save_m2m()

    @staticmethod
    def status_badge(obj):
        colors = {
            "pending": "orange",
            "confirmed": "blue",
            "rejected": "red",
        }
        color = colors.get(str(obj.status).lower(), "black")
        text = getattr(obj, "get_status_display", lambda: obj.status)()
        return format_html('<span style="color:{}; font-weight:600">{}</span>', color, text)

    @staticmethod
    def total_amount_display(obj):
        return f"{obj.total_amount:.2f}"

    @admin.display(description="Изм. долга")
    def debt_increase_display(self, obj):
        val = obj.debt_increase or Decimal("0")
        color = "red" if val > 0 else ("green" if val < 0 else "inherit")
        val_str = f"{val:.2f}"  # форматируем число заранее
        return format_html('<span style="color:{}">{}</span>', color, val_str)


# ---------- Admin: OrderReturn ----------

@admin.register(OrderReturn)
class OrderReturnAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "store_display",
        "partner_display",
        "status_badge",
        "total_amount_display",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("order__store__name", "order__partner__username", "reason")
    ordering = ("-created_at",)
    inlines = [OrderReturnItemInline]

    fieldsets = (
        ("Базовая информация", {"fields": ("order", "status", "reason")}),
        ("Сумма", {"fields": ("total_amount",)}),
        ("Системные поля", {"fields": ("created_at",)}),
    )
    readonly_fields = ("created_at",)

    @staticmethod
    def store_display(obj):
        return getattr(obj.order, "store", None)

    @staticmethod
    def partner_display(obj):
        return getattr(obj.order, "partner", None)

    @staticmethod
    def status_badge(obj):
        colors = {
            "pending": "orange",
            "approved": "green",
            "rejected": "red",
        }
        color = colors.get(str(obj.status).lower(), "black")
        text = getattr(obj, "get_status_display", lambda: obj.status)()
        return format_html('<span style="color:{}; font-weight:600">{}</span>', color, text)

    @staticmethod
    def total_amount_display(obj):
        return f"{obj.total_amount:.2f}"
