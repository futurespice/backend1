from decimal import Decimal

from django.contrib import admin, messages
from django.utils import timezone

from .models import (
    Expense,
    ProductExpense,
    MechanicalExpenseLog,
    CostSnapshot,
    BillOfMaterial,
    BOMLine,
)
from .calculators import (
    BomCostCalculator,
    BOMCycleError,
    BOMPriceResolveError,
    BOMNotFound,
    build_and_save_snapshot,
)

# ─────────────────────────────────────────
# Expense
# ─────────────────────────────────────────

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "type",
        "status",
        "state",
        "is_universal",
        "is_active",
        "price_per_unit",
        "unit",
        "created_at",
    )
    list_filter = ("type", "status", "state", "is_universal", "is_active")
    search_fields = ("name",)
    ordering = ("-id",)
    readonly_fields = ("created_at", "updated_at")


# ─────────────────────────────────────────
# ProductExpense (привязки)
# ─────────────────────────────────────────

@admin.register(ProductExpense)
class ProductExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "expense",
        "ratio_per_product_unit",
        "is_active",
    )
    list_filter = ("is_active", "expense__type")
    search_fields = ("product__name", "expense__name")
    autocomplete_fields = ("product", "expense")
    ordering = ("-id",)


# ─────────────────────────────────────────
# MechanicalExpenseLog
# ─────────────────────────────────────────

@admin.register(MechanicalExpenseLog)
class MechanicalExpenseLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "expense",
        "date",
        "quantity",
        "amount",
        "note",
    )
    list_filter = ("date", "expense__type")
    search_fields = ("expense__name", "note")
    autocomplete_fields = ("expense",)
    ordering = ("-date", "-id")


# ─────────────────────────────────────────
# CostSnapshot
# ─────────────────────────────────────────

@admin.register(CostSnapshot)
class CostSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "date",
        "produced_qty",
        "suzerain_input_amount",
        "physical_cost",
        "overhead_cost",
        "total_cost",
        "cost_per_unit",
        "revenue",
        "net_profit",
    )
    list_filter = ("date", "product")
    search_fields = ("product__name",)
    autocomplete_fields = ("product",)
    ordering = ("-date", "-id")
    readonly_fields = ("created_at", "updated_at", "breakdown")


# ─────────────────────────────────────────
# BOM (одна регистрация!)
# ─────────────────────────────────────────

class BOMLineInline(admin.TabularInline):
    model = BOMLine
    extra = 1
    autocomplete_fields = ("expense", "component_product")
    fields = ("expense", "component_product", "quantity", "unit", "is_primary")
    show_change_link = True


@admin.register(BillOfMaterial)
class BillOfMaterialAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "version", "is_active", "created_at", "updated_at")
    list_filter = ("is_active", "version")
    search_fields = ("product__name",)
    autocomplete_fields = ("product",)
    inlines = [BOMLineInline]
    ordering = ("-is_active", "product", "-version")
    readonly_fields = ("created_at", "updated_at")

    actions = ("action_check_cycles", "action_preview_cost_today", "action_make_snapshot_today")

    @admin.action(description="Проверить BOM на циклы")
    def action_check_cycles(self, request, queryset):
        as_of = timezone.localdate()
        calc = BomCostCalculator(as_of=as_of, strict_on_missing_bom=True)
        checked = 0
        errors = 0

        for bom in queryset.select_related("product"):
            try:
                calc.compute(bom.product_id)
                self.message_user(
                    request, f"[OK] {bom.product} — циклов не обнаружено.", level=messages.SUCCESS
                )
            except BOMCycleError as e:
                errors += 1
                chain = " → ".join(map(str, e.chain))
                self.message_user(
                    request, f"[CYCLE] {bom.product}: обнаружен цикл в BOM ({chain})", level=messages.ERROR
                )
            except BOMNotFound as e:
                errors += 1
                self.message_user(request, f"[MISSING] {bom.product}: {e}", level=messages.WARNING)
            except BOMPriceResolveError as e:
                errors += 1
                self.message_user(request, f"[PRICE] {bom.product}: {e}", level=messages.WARNING)
            except Exception as e:
                errors += 1
                self.message_user(request, f"[ERR] {bom.product}: {e}", level=messages.ERROR)
            finally:
                checked += 1

        if errors == 0:
            self.message_user(request, f"Проверено {checked} BOM — всё чисто ✅", level=messages.SUCCESS)
        else:
            self.message_user(request, f"Проверено {checked} BOM — проблем: {errors}", level=messages.WARNING)

    @admin.action(description="Превью себестоимости на сегодня (base/overheads/final)")
    def action_preview_cost_today(self, request, queryset):
        as_of = timezone.localdate()
        calc = BomCostCalculator(as_of=as_of)
        for bom in queryset.select_related("product"):
            try:
                res = calc.compute(bom.product_id)
                self.message_user(
                    request,
                    f"{bom.product} [{as_of}] → base={res.base_cost} | overheads={res.overheads_addon} | final={res.final_cost}",
                    level=messages.INFO,
                )
            except (BOMCycleError, BOMNotFound, BOMPriceResolveError) as e:
                self.message_user(request, f"{bom.product}: {e}", level=messages.WARNING)
            except Exception as e:
                self.message_user(request, f"{bom.product}: {e}", level=messages.ERROR)

    @admin.action(description="Создать снапшот на сегодня (через калькулятор 4.1)")
    def action_make_snapshot_today(self, request, queryset):
        today = timezone.localdate()
        made = 0
        for bom in queryset.select_related("product"):
            try:
                snap = build_and_save_snapshot(
                    product=bom.product,
                    date=today,
                    produced_qty=None,
                    suzerain_input_amount=None,
                    production_totals_by_product=None,
                    revenue=Decimal("0.00"),
                )
                self.message_user(
                    request,
                    f"Снапшот создан/обновлён: {bom.product} @ {today} (CPU={snap.cost_per_unit})",
                    level=messages.SUCCESS,
                )
                made += 1
            except Exception as e:
                self.message_user(request, f"{bom.product}: не удалось создать снапшот — {e}", level=messages.ERROR)

        if made:
            self.message_user(request, f"Создано/обновлено снапшотов: {made}", level=messages.SUCCESS)
