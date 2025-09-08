# products/admin.py
from decimal import Decimal
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.utils.html import format_html

from .models import ProductCategory, Product, ProductImage


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
            # ИСПРАВЛЕНО: Используем правильные константы из Product модели
            return qs.filter(
                (Q(category_type=Product.CategoryType.PIECE) & Q(stock_quantity__lt=10) & Q(stock_quantity__gt=0)) |
                (Q(category_type=Product.CategoryType.WEIGHT) & Q(stock_quantity__lt=Decimal("1.0")) & Q(
                    stock_quantity__gt=0))
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
        "is_bonus_eligible", "is_manufactured", "is_active", "is_available", "created_at",
    )
    list_filter = (
        "category", "category_type", LowStockFilter, InStockFilter,
        "is_active", "is_available", "is_bonus_eligible", "is_manufactured",
    )
    search_fields = ("name", "description")
    ordering = ("-created_at",)
    autocomplete_fields = ("category",)
    readonly_fields = ("created_at", "updated_at", "price_per_100g_display")
    inlines = [ProductImageInline]

    fieldsets = (
        ("Основное", {
            "fields": ("name", "description", "category", "category_type")
        }),
        ("Цены и количество", {
            "fields": ("price", "stock_quantity", "min_order_quantity")
        }),
        ("Производство", {
            "fields": ("is_manufactured", "manufacturing_time_minutes"),
            "classes": ("collapse",)
        }),
        ("Бонусы", {
            "fields": ("is_bonus_eligible", "bonus_every_n"),
            "classes": ("collapse",)
        }),
        ("Статусы", {
            "fields": ("is_active", "is_available")
        }),
        ("Системные поля", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    @admin.display(description="Цена за 100г", ordering="price")
    def price_per_100g_display(self, obj):
        """Отображение цены за 100г для весовых товаров"""
        if obj.category_type == Product.CategoryType.WEIGHT:
            price_per_100g = obj.price * Decimal('0.1')  # цена за кг / 10
            return f"{price_per_100g:.2f} сом"
        return "—"

    def get_queryset(self, request):
        """Оптимизируем запросы"""
        qs = super().get_queryset(request)
        return qs.select_related('category').prefetch_related('images')

    def save_model(self, request, obj, form, change):
        """Дополнительные проверки при сохранении"""
        # Автоматически устанавливаем тип товара из категории если не задан
        if obj.category and not obj.category_type:
            obj.category_type = obj.category.category_type

        # Весовые товары не могут участвовать в бонусах
        if obj.category_type == Product.CategoryType.WEIGHT:
            obj.is_bonus_eligible = False

        super().save_model(request, obj, form, change)

    actions = ['make_active', 'make_inactive', 'reset_stock', 'bulk_price_update']

    @admin.action(description='Активировать выбранные товары')
    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True, is_available=True)
        self.message_user(request, f'{updated} товаров активированы.')

    @admin.action(description='Деактивировать выбранные товары')
    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False, is_available=False)
        self.message_user(request, f'{updated} товаров деактивированы.')

    @admin.action(description='Обнулить остатки')
    def reset_stock(self, request, queryset):
        updated = queryset.update(stock_quantity=0)
        self.message_user(request, f'Остатки обнулены для {updated} товаров.')

    @admin.action(description='Массовое изменение цен')
    def bulk_price_update(self, request, queryset):
        # Простая реализация - можно расширить
        self.message_user(request, 'Функция массового изменения цен в разработке.')


# ---------- Product Images ----------
@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'image', 'is_primary', 'order', 'created_at')
    list_filter = ('is_primary', 'created_at')
    search_fields = ('product__name',)
    ordering = ('product__name', 'order')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')