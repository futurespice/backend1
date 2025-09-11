from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import Q, Count, Sum, Avg
from .models import Category, Product, ProductPriceHistory
from .serializers import (
    CategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductCreateUpdateSerializer,
    ProductPriceHistorySerializer,
    ProductAnalyticsSerializer,
    ProductStockUpdateSerializer
)
from users.permissions import IsAdminUser, IsPartnerUser
from django.db import models


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для категорий товаров"""

    queryset = Category.objects.filter(is_active=True).order_by('sort_order', 'name')
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['parent']
    search_fields = ['name', 'description']

    def get_queryset(self):
        qs = super().get_queryset()

        # Фильтр по уровню (корневые категории)
        if self.request.query_params.get('root_only') == 'true':
            qs = qs.filter(parent=None)

        return qs

    @action(detail=True, methods=['get'])
    def products(self, request, pk=None):
        """Получить товары категории"""
        category = self.get_object()

        # Получаем товары категории и всех подкатегорий
        category_ids = [category.id] + [child.id for child in category.get_all_children()]

        products = Product.objects.filter(
            category_id__in=category_ids,
            is_active=True
        ).select_related('category')

        # Применяем фильтры
        if request.query_params.get('available_only') == 'true':
            products = products.filter(is_available=True, stock_quantity__gt=0)

        page = self.paginate_queryset(products)
        if page is not None:
            serializer = ProductListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)


class ProductViewSet(viewsets.ModelViewSet):
    """ViewSet для товаров"""

    queryset = Product.objects.filter(is_active=True).select_related('category')
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'unit', 'is_available', 'is_bonus_eligible']
    search_fields = ['name', 'description', 'article']
    ordering_fields = ['name', 'price', 'created_at', 'stock_quantity']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProductCreateUpdateSerializer
        else:
            return ProductDetailSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # Партнёры видят только доступные товары
        if user.role == 'partner':
            qs = qs.filter(is_available=True)

        # Фильтры по наличию
        if self.request.query_params.get('in_stock') == 'true':
            qs = qs.filter(stock_quantity__gt=0)

        if self.request.query_params.get('low_stock') == 'true':
            qs = qs.filter(stock_quantity__lte=models.F('low_stock_threshold'))

        # Фильтр по цене
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')

        if min_price:
            qs = qs.filter(price__gte=min_price)
        if max_price:
            qs = qs.filter(price__lte=max_price)

        return qs

    @action(detail=True, methods=['get'])
    def price_history(self, request, pk=None):
        """История изменения цен товара"""
        product = self.get_object()
        history = ProductPriceHistory.objects.filter(product=product).order_by('-created_at')

        page = self.paginate_queryset(history)
        if page is not None:
            serializer = ProductPriceHistorySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProductPriceHistorySerializer(history, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def update_stock(self, request):
        """Массовое обновление остатков товаров"""
        serializer = ProductStockUpdateSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        updated_products = []

        for item_data in serializer.validated_data:
            try:
                product = Product.objects.get(id=item_data['product_id'])
                quantity = item_data['quantity']
                operation = item_data['operation']

                if operation == 'add':
                    product.stock_quantity += quantity
                elif operation == 'subtract':
                    product.stock_quantity = max(0, product.stock_quantity - quantity)
                elif operation == 'set':
                    product.stock_quantity = quantity

                product.save(update_fields=['stock_quantity'])
                updated_products.append({
                    'product_id': product.id,
                    'name': product.name,
                    'old_quantity': product.stock_quantity,
                    'new_quantity': product.stock_quantity
                })

            except Product.DoesNotExist:
                continue

        return Response({
            'message': f'Обновлено {len(updated_products)} товаров',
            'updated_products': updated_products
        })

    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """Аналитика по товарам"""
        queryset = self.get_queryset()

        # Базовая статистика
        total_products = queryset.count()
        active_products = queryset.filter(is_available=True).count()
        low_stock_products = queryset.filter(
            stock_quantity__lte=models.F('low_stock_threshold')
        ).count()
        out_of_stock_products = queryset.filter(stock_quantity=0).count()

        # Средняя цена и общая стоимость склада
        aggregates = queryset.aggregate(
            avg_price=Avg('price'),
            total_stock_value=Sum(models.F('stock_quantity') * models.F('price'))
        )

        # Топ категории по количеству товаров
        top_categories = Category.objects.filter(
            products__in=queryset
        ).annotate(
            products_count=Count('products')
        ).order_by('-products_count')[:5].values('name', 'products_count')

        # Распределение по ценовым диапазонам
        price_ranges = {
            '0-100': queryset.filter(price__lt=100).count(),
            '100-500': queryset.filter(price__gte=100, price__lt=500).count(),
            '500-1000': queryset.filter(price__gte=500, price__lt=1000).count(),
            '1000+': queryset.filter(price__gte=1000).count(),
        }

        analytics_data = {
            'total_products': total_products,
            'active_products': active_products,
            'low_stock_products': low_stock_products,
            'out_of_stock_products': out_of_stock_products,
            'average_price': aggregates['avg_price'] or 0,
            'total_stock_value': aggregates['total_stock_value'] or 0,
            'top_categories': list(top_categories),
            'price_ranges': price_ranges
        }

        serializer = ProductAnalyticsSerializer(analytics_data)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Товары с низким остатком"""
        products = self.get_queryset().filter(
            stock_quantity__lte=models.F('low_stock_threshold')
        ).order_by('stock_quantity')

        page = self.paginate_queryset(products)
        if page is not None:
            serializer = ProductListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def popular(self, request):
        """Популярные товары (по количеству заказов)"""
        from apps.orders.models import OrderItem

        # Получаем товары с количеством заказов
        popular_products = self.get_queryset().annotate(
            orders_count=Count('orderitem', distinct=True),
            total_sold=Sum('orderitem__quantity')
        ).filter(
            orders_count__gt=0
        ).order_by('-orders_count', '-total_sold')

        page = self.paginate_queryset(popular_products)
        if page is not None:
            serializer = ProductListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = ProductListSerializer(popular_products, many=True, context={'request': request})
        return Response(serializer.data)