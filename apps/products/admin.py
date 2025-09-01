from django.contrib import admin
from django.utils.html import format_html
from .models import ProductCategory, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image', 'is_primary', 'order')
    ordering = ('order',)


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'category_type', 'products_count', 'is_active', 'created_at')
    list_filter = ('category_type', 'is_active')
    search_fields = ('name',)
    ordering = ('name',)

    def products_count(self, obj):
        return obj.products.count()

    products_count.short_description = 'Количество товаров'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category_type', 'price', 'stock_quantity', 'is_bonus_eligible', 'is_active', 'created_at')
    list_filter = ('category_type', 'is_bonus_eligible', 'is_active', 'is_available', 'category')
    search_fields = ('name', 'description')
    ordering = ('-created_at',)

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'description', 'category', 'category_type')
        }),
        ('Цена и количество', {
            'fields': ('price', 'stock_quantity', 'min_order_quantity')
        }),
        ('Настройки', {
            'fields': ('is_bonus_eligible', 'is_active', 'is_available')
        }),
    )

    inlines = [ProductImageInline]

    actions = ['activate_products', 'deactivate_products', 'make_bonus_eligible', 'make_not_bonus_eligible']

    def activate_products(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} товаров активировано.')

    activate_products.short_description = "Активировать выбранные товары"

    def deactivate_products(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} товаров деактивировано.')

    deactivate_products.short_description = "Деактивировать выбранные товары"

    def make_bonus_eligible(self, request, queryset):
        # Только для штучных товаров
        updated = queryset.filter(category_type='piece').update(is_bonus_eligible=True)
        self.message_user(request, f'{updated} товаров включено в бонусную программу.')

    make_bonus_eligible.short_description = "Включить в бонусную программу"

    def make_not_bonus_eligible(self, request, queryset):
        updated = queryset.update(is_bonus_eligible=False)
        self.message_user(request, f'{updated} товаров исключено из бонусной программы.')

    make_not_bonus_eligible.short_description = "Исключить из бонусной программы"


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'image_preview', 'is_primary', 'order', 'created_at')
    list_filter = ('is_primary',)
    ordering = ('product__name', 'order')

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit: cover;" />', obj.image.url)
        return "Нет изображения"

    image_preview.short_description = "Превью"