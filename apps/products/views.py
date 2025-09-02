from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from decimal import Decimal
from django.db import models

from .models import Product, ProductCategory, ProductImage
from .serializers import (
    ProductListSerializer, ProductDetailSerializer, ProductCreateUpdateSerializer,
    ProductCategorySerializer, ProductPriceCalculationSerializer,
    ProductStockUpdateSerializer, ProductRequestSerializer
)
from .filters import ProductFilter
from users.permissions import IsAdminUser, IsPartnerUser, IsStoreUser


class ProductCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API категорий товаров"""
    queryset = ProductCategory.objects.filter(is_active=True)
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering = ['name']


class ProductViewSet(viewsets.ModelViewSet):
    """API товаров"""
    queryset = Product.objects.select_related('category').prefetch_related('images')
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'price', 'created_at', 'stock_quantity']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProductCreateUpdateSerializer
        return ProductDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Для партнеров и магазинов показываем только активные товары
        if self.request.user.role in ['partner', 'store']:
            queryset = queryset.filter(is_active=True, is_available=True)

        return queryset

    def get_permissions(self):
        """Разные права для разных действий"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsAdminUser]
        elif self.action in ['calculate_price', 'request_products']:
            permission_classes = [IsPartnerUser | IsStoreUser]
        else:
            permission_classes = [permissions.IsAuthenticated]

        return [permission() for permission in permission_classes]

    @action(detail=True, methods=['post'])
    def calculate_price(self, request, pk=None):
        """Рассчитать цену для указанного количества"""
        product = self.get_object()
        serializer = ProductPriceCalculationSerializer(
            data=request.data,
            context={'product': product}
        )

        if serializer.is_valid():
            quantity = serializer.validated_data['quantity']
            total_price = product.calculate_price(quantity)

            return Response({
                'product_id': product.id,
                'product_name': product.name,
                'quantity': quantity,
                'unit_price': product.price,
                'price_per_100g': product.price_per_100g,
                'total_price': total_price,
                'category_type': product.category_type
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def update_stock(self, request, pk=None):
        """Обновить остатки товара (только для админа)"""
        product = self.get_object()
        serializer = ProductStockUpdateSerializer(data=request.data)

        if serializer.is_valid():
            quantity = serializer.validated_data['quantity']
            operation = serializer.validated_data['operation']
            reason = serializer.validated_data.get('reason', '')

            old_quantity = product.stock_quantity

            if operation == 'add':
                product.increase_stock(quantity)
            elif operation == 'subtract':
                if not product.reduce_stock(quantity):
                    return Response(
                        {'error': 'Недостаточно товара на складе'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            elif operation == 'set':
                product.stock_quantity = quantity
                product.save()

            # Логирование изменения остатков
            from reports.models import ExpenseRecord
            if operation != 'add':
                ExpenseRecord.objects.create(
                    partner=request.user if request.user.role == 'partner' else None,
                    amount=0,  # Изменение остатков, не финансовый расход
                    expense_type='other',
                    description=f'Изменение остатков {product.name}: {old_quantity} -> {product.stock_quantity}. {reason}'
                )

            return Response({
                'product_id': product.id,
                'old_quantity': old_quantity,
                'new_quantity': product.stock_quantity,
                'operation': operation,
                'reason': reason
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Получить список категорий с товарами"""
        categories = ProductCategory.objects.filter(
            is_active=True,
            products__is_active=True
        ).distinct().annotate(
            products_count=models.Count('products')
        )

        serializer = ProductCategorySerializer(categories, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def bonus_eligible(self, request):
        """Товары, участвующие в бонусной программе"""
        products = self.get_queryset().filter(
            is_bonus_eligible=True,
            category_type='piece'  # Только штучные товары могут быть бонусными
        )

        page = self.paginate_queryset(products)
        if page is not None:
            serializer = ProductListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def weight_products(self, request):
        """Весовые товары"""
        products = self.get_queryset().filter(category_type='weight')

        page = self.paginate_queryset(products)
        if page is not None:
            serializer = ProductListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Товары с низким остатком (меньше 10 для штучных, меньше 1кг для весовых)"""
        low_stock_products = []

        for product in self.get_queryset():
            if product.category_type == 'piece' and product.stock_quantity < 10:
                low_stock_products.append(product)
            elif product.category_type == 'weight' and product.stock_quantity < 1:
                low_stock_products.append(product)

        serializer = ProductListSerializer(low_stock_products, many=True, context={'request': request})
        return Response(serializer.data)