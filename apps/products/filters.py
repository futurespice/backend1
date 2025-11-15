import django_filters
from django.db.models import Q
from decimal import Decimal

from .models import Product


class ProductFilter(django_filters.FilterSet):
    """Фильтры для товаров"""
    # Ценовые фильтры
    price_min = django_filters.NumberFilter(field_name='price', lookup_expr='gte')
    price_max = django_filters.NumberFilter(field_name='price', lookup_expr='lte')

    # Остатки
    in_stock = django_filters.BooleanFilter(method='filter_in_stock')
    low_stock = django_filters.BooleanFilter(method='filter_low_stock')
    stock_min = django_filters.NumberFilter(field_name='stock_quantity', lookup_expr='gte')
    stock_max = django_filters.NumberFilter(field_name='stock_quantity', lookup_expr='lte')

    # Бонусная система
    bonus_eligible = django_filters.BooleanFilter(field_name='is_bonus_eligible')

    # Статусы
    is_active = django_filters.BooleanFilter()
    is_available = django_filters.BooleanFilter()

    # Поиск
    search = django_filters.CharFilter(method='filter_search')

    class Meta:
        model = Product
        fields = [
            'is_active', 'is_available',
            'is_bonus_eligible'
        ]

    def filter_in_stock(self, queryset, name, value):
        """Фильтр товаров в наличии"""
        if value is True:
            return queryset.filter(stock_quantity__gt=0)
        elif value is False:
            return queryset.filter(stock_quantity=0)
        return queryset

    def filter_low_stock(self, queryset, name, value):
        """Фильтр товаров с низким остатком"""
        threshold = Decimal('10')  # Можно вынести в настройки

        if value is True:
            return queryset.filter(
                stock_quantity__gt=0,
                stock_quantity__lt=threshold
            )
        elif value is False:
            return queryset.filter(
                Q(stock_quantity=0) | Q(stock_quantity__gte=threshold)
            )
        return queryset

    def filter_search(self, queryset, name, value):
        """Поиск по названию и описанию"""
        if not value:
            return queryset

        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value)
        )