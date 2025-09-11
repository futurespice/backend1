from django.contrib import admin
from .models import Category, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ['image', 'alt_text', 'is_primary', 'order']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    list_editable = ['is_active']
    ordering = ['name']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'description', 'parent')
        }),
        ('Изображение', {
            'fields': ('image',)
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('parent')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'sku', 'category', 'price', 'unit',
        'stock_quantity', 'is_available', 'is_active'
    ]
    list_filter = ['category', 'unit', 'is_available', 'is_active', 'created_at']
    search_fields = ['name', 'sku', 'description']
    list_editable = ['price', 'is_available', 'is_active']
    ordering = ['name']
    inlines = [ProductImageInline]

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'description', 'category', 'sku')
        }),
        ('Цена и единицы', {
            'fields': ('price', 'unit', 'min_order_quantity')
        }),
        ('Складские остатки', {
            'fields': ('stock_quantity', 'low_stock_threshold')
        }),
        ('Статус', {
            'fields': ('is_available', 'is_active')
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category')


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['product', 'alt_text', 'is_primary', 'order', 'created_at']
    list_filter = ['is_primary', 'created_at']
    search_fields = ['product__name', 'alt_text']
    list_editable = ['is_primary', 'order']
    ordering = ['product', 'order']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')