# products/filters.py
import django_filters
from decimal import Decimal
from django.db import models
from django_filters import rest_framework as drf_filters

from .models import Product, ProductCategory, Unit, ProductBOM


class ProductFilter(django_filters.FilterSet):
    """
    Расширенные фильтры для товаров.

    Поддерживает:
    - тип товара (штучный/весовой),
    - категорию (одну или несколько), — диапазон цены,
    - наличие / низкий остаток / отсутствие на складе,
    - только бонусные (штучные),
    - наличие изображений,
    - наличие/отсутствие состава (BOM),
    - диапазон дат создания.
    """

    # Базовые
    category_type = django_filters.ChoiceFilter(choices=Unit.CHOICES)
    category = django_filters.ModelChoiceFilter(
        queryset=ProductCategory.objects.filter(is_active=True)
    )
    categories = django_filters.ModelMultipleChoiceFilter(
        field_name="category",
        to_field_name="id",
        queryset=ProductCategory.objects.filter(is_active=True),
        label="Несколько категорий",
    )
    is_bonus_eligible = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()
    is_available = django_filters.BooleanFilter()

    # Цена
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    price_range = drf_filters.RangeFilter(field_name="price")  # ?price_range_min=&price_range_max=

    # Остатки
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")
    low_stock = django_filters.BooleanFilter(method="filter_low_stock")
    out_of_stock = django_filters.BooleanFilter(method="filter_out_of_stock")

    # Дополнительно
    bonus_only = django_filters.BooleanFilter(method="filter_bonus_only")
    has_images = django_filters.BooleanFilter(method="filter_has_images")
    has_bom = django_filters.BooleanFilter(method="filter_has_bom")

    # Дата
    created_between = drf_filters.DateFromToRangeFilter(field_name="created_at")
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Product
        fields = [
            "category_type", "category", "categories",
            "is_bonus_eligible", "is_active", "is_available",
            "in_stock", "low_stock", "out_of_stock",
            "has_images", "has_bom", "created_between",
        ]

    # ---------- методы ----------

    def filter_in_stock(self, queryset, name, value):
        """В наличии (stock > 0) или нет (stock = 0)."""
        if value is None:
            return queryset
        return queryset.filter(stock_quantity__gt=0) if value else queryset.filter(stock_quantity=0)

    def filter_out_of_stock(self, queryset, name, value):
        """Нет в наличии."""
        if value is None:
            return queryset
        return queryset.filter(stock_quantity=0) if value else queryset.filter(stock_quantity__gt=0)

    def filter_low_stock(self, queryset, name, value):
        """
        Низкий остаток:
        - штучные: < 10 и > 0
        - весовые: < 1.0 кг и > 0
        Реализовано через annotate+Case, без union.
        """
        if value is None:
            return queryset

        low_piece = models.Case(
            models.When(
                models.Q(category_type=Unit.PIECE) &
                models.Q(stock_quantity__lt=Decimal("10")) &
                models.Q(stock_quantity__gt=0),
                then=models.Value(True),
            ),
            default=models.Value(False),
            output_field=models.BooleanField(),
        )
        low_weight = models.Case(
            models.When(
                models.Q(category_type=Unit.WEIGHT) &
                models.Q(stock_quantity__lt=Decimal("1.0")) &
                models.Q(stock_quantity__gt=0),
                then=models.Value(True),
            ),
            default=models.Value(False),
            output_field=models.BooleanField(),
        )

        qs = queryset.annotate(_low_piece=low_piece, _low_weight=low_weight)
        return qs.filter(models.Q(_low_piece=True) | models.Q(_low_weight=True)) if value else qs.exclude(
            models.Q(_low_piece=True) | models.Q(_low_weight=True)
        )

    def filter_bonus_only(self, queryset, name, value):
        """Только бонусные (штучные) или исключить бонусные."""
        if value is None:
            return queryset
        if value:
            return queryset.filter(category_type=Unit.PIECE, is_bonus_eligible=True)
        return queryset.exclude(is_bonus_eligible=True)

    def filter_has_images(self, queryset, name, value):
        """Есть ли картинки (любые) у товара."""
        if value is None:
            return queryset
        return (
            queryset.filter(images__isnull=False).distinct()
            if value
            else queryset.filter(images__isnull=True)
        )

    def filter_has_bom(self, queryset, name, value):
        """Есть ли у товара состав (BOM)."""
        if value is None:
            return queryset
        # Наличие хотя бы одного ProductBOM для данного product
        has_bom_ids = ProductBOM.objects.values_list("product_id", flat=True).distinct()
        return (
            queryset.filter(id__in=has_bom_ids)
            if value
            else queryset.exclude(id__in=has_bom_ids)
        )
