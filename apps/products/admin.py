from django.contrib import admin
from .models import Category, Product, ProductImage, ProductCharacteristic

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ['image', 'title', 'sort_order']

class ProductCharacteristicInline(admin.TabularInline):
    model = ProductCharacteristic
    extra = 1
    fields = ['name', 'value', 'unit', 'sort_order']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'is_active', 'sort_order', 'created_at']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'description']
    ordering = ['sort_order', 'name']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'article', 'category', 'price', 'stock_quantity',
        'is_active', 'is_available', 'created_at'
    ]
    list_filter = ['is_active', 'is_available', 'category', 'unit']
    search_fields = ['name', 'description', 'article']
    ordering = ['name']
    inlines = [ProductImageInline, ProductCharacteristicInline]
    prepopulated_fields = {'slug': ('name',)}

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'description', 'article', 'slug', 'category')
        }),
        ('Цены', {
            'fields': ('price', 'cost_price', 'unit')
        }),
        ('Остатки', {
            'fields': ('stock_quantity', 'low_stock_threshold')
        }),
        ('Бонусы', {
            'fields': ('is_bonus_eligible', 'bonus_points')
        }),
        ('Изображения', {
            'fields': ('main_image',)
        }),
        ('Характеристики', {
            'fields': ('weight', 'volume')
        }),
        ('Статусы', {
            'fields': ('is_active', 'is_available')
        }),
        ('Производство', {
            'fields': ('production_time_days', 'shelf_life_days')
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['product', 'title', 'sort_order']
    list_filter = ['product']
    ordering = ['product', 'sort_order']