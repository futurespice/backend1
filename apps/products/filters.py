import django_filters
from .models import Product, ProductCategory
from decimal import Decimal


class ProductFilter(django_filters.FilterSet):
    """Фильтры для товаров"""

    # Основные фильтры
    category_type = django_filters.ChoiceFilter(choices=Product.CATEGORY_TYPES)
    category = django_filters.ModelChoiceFilter(queryset=ProductCategory.objects.filter(is_active=True))
    is_bonus_eligible = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()
    is_available = django_filters.BooleanFilter()

    # Фильтр по цене
    min_price = django_filters.NumberFilter(field_name='price', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='price', lookup_expr='lte')
    price_range = django_filters.RangeFilter(field_name='price')

    # Фильтр по остаткам
    in_stock = django_filters.BooleanFilter(method='filter_in_stock')
    low_stock = django_filters.BooleanFilter(method='filter_low_stock')
    out_of_stock = django_filters.BooleanFilter(method='filter_out_of_stock')

    # Фильтр по дате создания
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = Product
        fields = [
            'category_type', 'category', 'is_bonus_eligible',
            'is_active', 'is_available', 'in_stock', 'low_stock'
        ]

    def filter_in_stock(self, queryset, name, value):
        """Фильтр товаров в наличии"""
        if value:
            return queryset.filter(stock_quantity__gt=0)
        return queryset.filter(stock_quantity=0)

    def filter_low_stock(self, queryset, name, value):
        """Фильтр товаров с низким остатком"""
        if value:
            # Для штучных товаров - меньше 10, для весовых - меньше 1кг
            piece_products = queryset.filter(
                category_type='piece',
                stock_quantity__lt=10,
                stock_quantity__gt=0
            )
            weight_products = queryset.filter(
                category_type='weight',
                stock_quantity__lt=Decimal('1.0'),
                stock_quantity__gt=0
            )
            return piece_products.union(weight_products)
        return queryset

    def filter_out_of_stock(self, queryset, name, value):
        """Фильтр товаров не в наличии"""
        if value:
            return queryset.filter(stock_quantity=0)
        return queryset.filter(stock_quantity__gt=0)