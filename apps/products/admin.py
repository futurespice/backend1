# products/admin.py
from decimal import Decimal
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.utils.html import format_html

from .models import ProductCategory, Product, ProductImage, Unit


# ---------- Inlines ----------
class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ("image", "is_primary", "order")
    ordering = ("order",)


# ---------- Custom list filters ----------
class InStockFilter(admin.SimpleListFilter):
    title = "Наличие"
    parameter_name = "in_stock"

    def lookups(self, request, model_admin):
        return (("1", "В наличии"), ("0", "Нет в наличии"),)

    def queryset(self, request, qs):
        if self.value() == "1":
            return qs.filter(stock_quantity__gt=0)
        if self.value() == "0":
            return qs.filter(stock_quantity=0)
        return qs


class LowStockFilter(admin.SimpleListFilter):
    title = "Низкий остаток"
    parameter_name = "low_stock"

    def lookups(self, request, model_admin):
        return (("1", "Показать только низкие"),)

    def queryset(self, request, qs):
        if self.value() == "1":
            return qs.filter(
                (Q(category_type=Unit.PIECE) & Q(stock_quantity__lt=10) & Q(stock_quantity__gt=0)) |
                (Q(category_type=Unit.WEIGHT) & Q(stock_quantity__lt=Decimal("1.0")) & Q(stock_quantity__gt=0))
            )
        return qs


# ---------- Category ----------
@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category_type", "products_count", "is_active", "created_at")
    list_filter = ("category_type", "is_active")
    search_fields = ("name",)
    ordering = ("name",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # считаем только активные товары в категории
        return qs.annotate(_products_count=Count("products", filter=Q(products__is_active=True)))

    @admin.display(description="Кол-во товаров", ordering="_products_count")
    def products_count(self, obj):
        return obj._products_count


# ---------- Product ----------
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name", "category", "category_type", "price",
        "stock_quantity", "min_order_quantity",
        "price_per_100g_display",
        "is_bonus_eligible", "is_active", "is_available", "created_at",
    )
    list_filter = (
        "category", "category_type", LowStockFilter, InStockFilter,
        "is_active", "is_available", "is_bonus_eligible",
    )
    search_fields = ("name", "description")
    ordering = ("-created_at",)
    autocomplete_fields = ("category",)
    readonly_fields = ("created_at", "updated_at", "price_per_100g_display")

    fieldsets = (
        ("Основное", {"fields": ("name", "description", "category", "category_type")}),
        ("Цена и остатки", {"fields": ("price", "stock_quantity", "min_order_quantity", "price_per_100g_display")}),
        ("Статусы", {"fields": ("is_bonus_eligible", "is_active", "is_available")}),
        ("Системные", {"fields": ("created_at", "updated_at")}),
    )

    inlines = [ProductImageInline]

    # — actions —
    actions = [
        "activate_products", "deactivate_products",
        "make_available", "make_unavailable",
        "make_bonus_eligible", "make_not_bonus_eligible",
    ]

    # показываем цену за 100 г только для весовых
    @admin.display(description="Цена за 100 г")
    def price_per_100g_display(self, obj: Product):
        return obj.price_per_100g if obj.category_type == Unit.WEIGHT else "-"

    # делаем поле бонусов read-only для весовых (защита в админ-форме)
    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj and obj.category_type == Unit.WEIGHT and "is_bonus_eligible" not in ro:
            ro.append("is_bonus_eligible")
        return ro

    # оптимизируем выборку
    def get_queryset(self, request):
        return super().get_queryset(request).select_related("category").prefetch_related("images")

    # ---- actions impl ----
    def activate_products(self, request, qs):
        updated = qs.update(is_active=True)
        self.message_user(request, f"{updated} товаров активировано.", messages.SUCCESS)

    activate_products.short_description = "Активировать выбранные"

    def deactivate_products(self, request, qs):
        updated = qs.update(is_active=False)
        self.message_user(request, f"{updated} товаров деактивировано.", messages.SUCCESS)

    deactivate_products.short_description = "Деактивировать выбранные"

    def make_available(self, request, qs):
        updated = qs.update(is_available=True)
        self.message_user(request, f"{updated} товаров доступны к заказу.", messages.SUCCESS)

    make_available.short_description = "Сделать доступными к заказу"

    def make_unavailable(self, request, qs):
        updated = qs.update(is_available=False)
        self.message_user(request, f"{updated} товаров недоступны к заказу.", messages.SUCCESS)

    make_unavailable.short_description = "Сделать недоступными к заказу"

    def make_bonus_eligible(self, request, qs):
        # только штучные; весовые — игнорируем
        updated = qs.filter(category_type=Unit.PIECE).update(is_bonus_eligible=True)
        skipped = qs.filter(category_type=Unit.WEIGHT).count()
        msg = f"{updated} штучных товаров включены в бонусную программу."
        if skipped:
            msg += f" {skipped} весовых пропущены."
        self.message_user(request, msg, messages.INFO)

    make_bonus_eligible.short_description = "Включить в бонусную программу (штучные)"

    def make_not_bonus_eligible(self, request, qs):
        updated = qs.update(is_bonus_eligible=False)
        self.message_user(request, f"{updated} товаров исключено из бонусной программы.", messages.INFO)

    make_not_bonus_eligible.short_description = "Исключить из бонусной программы"


# ---------- Images ----------
@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "image_preview", "is_primary", "order", "created_at")
    list_filter = ("is_primary",)
    search_fields = ("product__name",)
    ordering = ("product__name", "order")

    @admin.display(description="Превью")
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit:cover;border-radius:6px" />', obj.image.url)
        return "—"

    actions = ["set_as_primary"]

    def set_as_primary(self, request, qs):
        """
        Сделать выбранные изображения основными для их товара.
        Для каждого товара оставляем основным только одно.
        """
        affected = 0
        for img in qs.select_related("product"):
            img.product.images.update(is_primary=False)
            img.is_primary = True
            img.save(update_fields=["is_primary"])
            affected += 1
        self.message_user(request, f"Обновлено: {affected} основн. изображений.", messages.SUCCESS)

    set_as_primary.short_description = "Сделать основным"
