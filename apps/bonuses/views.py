from rest_framework import viewsets, permissions, status, generics
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import Sum, Count, Q
from datetime import datetime
from rest_framework import serializers
from .models import BonusRule, BonusHistory, BonusCalculator  # ИСПРАВЛЕНО: BonusCalculator вместо BonusCalculation
from .serializers import (
    BonusRuleSerializer, BonusHistorySerializer,
    BonusCalculationSerializer, BonusAnalyticsSerializer
)
from apps.users.permissions import IsAdminUser


class BonusRuleViewSet(viewsets.ModelViewSet):
    """ViewSet для правил бонусов"""

    queryset = BonusRule.objects.prefetch_related('products')
    serializer_class = BonusRuleSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['is_active', 'applies_to_all_products']
    search_fields = ['name', 'description']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()

        # Не-админы видят только активные правила
        if not (hasattr(self.request.user, 'role') and self.request.user.role == 'admin'):
            qs = qs.filter(is_active=True)

        return qs


class BonusHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для истории бонусов (только чтение)"""

    queryset = BonusHistory.objects.select_related(
        'store', 'product', 'order'
    )
    serializer_class = BonusHistorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['store', 'product', 'order']
    search_fields = ['store__store_name', 'product__name']
    ordering_fields = ['created_at', 'discount_amount']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.role == 'store':
            # Магазин видит только свою историю бонусов
            qs = qs.filter(store__user=user)
        elif user.role == 'partner':
            # Партнёр видит историю своих магазинов
            qs = qs.filter(store__partner=user)

        return qs


class BonusBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для баланса бонусов (только чтение)"""

    from .models import BonusBalance
    from .serializers import BonusBalanceSerializer

    queryset = BonusBalance.objects.select_related('store', 'store__user')
    serializer_class = BonusBalanceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['store']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.role == 'store':
            # Магазин видит только свой баланс
            qs = qs.filter(store__user=user)
        elif user.role == 'partner':
            # Партнёр видит балансы своих магазинов
            qs = qs.filter(store__partner=user)

        return qs


class BonusCalculationView(generics.GenericAPIView):
    """Расчёт бонусов для корзины товаров"""

    serializer_class = BonusCalculationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        Рассчитать бонусы для корзины товаров

        Request data:
        {
            "items": [
                {"product_id": 1, "quantity": 5},
                {"product_id": 2, "quantity": 3}
            ]
        }
        """
        items = request.data.get('items', [])

        if not items:
            return Response(
                {'error': 'Список товаров не может быть пустым'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Получаем магазин
        try:
            store = request.user.store_profile
        except:
            return Response(
                {'error': 'Пользователь не является магазином'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from apps.products.models import Product

        results = []
        total_bonus_discount = 0

        for item in items:
            try:
                product = Product.objects.get(id=item['product_id'])
                quantity = float(item['quantity'])

                # Используем BonusCalculator для расчёта
                bonuses = BonusCalculator.calculate_order_bonuses(
                    [{
                        'product': product,
                        'quantity': quantity,
                        'unit_price': product.price
                    }],
                    store
                )

                bonus_discount = bonuses.get('discount_amount', 0)
                bonus_items = bonuses.get('bonus_items', 0)

                result = {
                    'product_id': product.id,
                    'product_name': product.name,
                    'quantity': quantity,
                    'unit_price': float(product.price),
                    'bonus_quantity': bonus_items,
                    'bonus_discount': float(bonus_discount)
                }
                results.append(result)
                total_bonus_discount += bonus_discount

            except Product.DoesNotExist:
                continue
            except (ValueError, KeyError):
                continue

        return Response({
            'items': results,
            'total_bonus_discount': float(total_bonus_discount)
        })


class BonusAnalyticsView(generics.GenericAPIView):
    """Аналитика по бонусам"""

    serializer_class = BonusAnalyticsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        Получить аналитику по бонусам

        Query params:
        - store_id: ID магазина
        - product_id: ID товара
        - date_from: Дата начала (YYYY-MM-DD)
        - date_to: Дата окончания (YYYY-MM-DD)
        """
        user = self.request.user

        # Базовая фильтрация по ролям
        history_qs = BonusHistory.objects.all()

        if user.role == 'store':
            history_qs = history_qs.filter(store__user=user)
        elif user.role == 'partner':
            history_qs = history_qs.filter(store__partner=user)

        # Фильтры из query params
        store_id = request.query_params.get('store_id')
        product_id = request.query_params.get('product_id')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        if store_id:
            history_qs = history_qs.filter(store_id=store_id)
        if product_id:
            history_qs = history_qs.filter(product_id=product_id)
        if date_from:
            history_qs = history_qs.filter(created_at__date__gte=date_from)
        if date_to:
            history_qs = history_qs.filter(created_at__date__lte=date_to)

        # Агрегированная статистика
        stats = history_qs.aggregate(
            total_bonus_items=Sum('bonus_items'),
            total_discount=Sum('discount_amount'),
            total_orders=Count('order', distinct=True),
            total_products=Count('product', distinct=True)
        )

        # Топ товары по бонусам
        top_products = history_qs.values(
            'product__name', 'product_id'
        ).annotate(
            bonus_count=Sum('bonus_items'),
            discount_amount=Sum('discount_amount')
        ).order_by('-bonus_count')[:5]

        # Топ магазины по бонусам (только для админов и партнёров)
        top_stores = []
        if user.role in ['admin', 'partner']:
            store_filter = history_qs
            if user.role == 'partner':
                store_filter = store_filter.filter(store__partner=user)

            top_stores = store_filter.values(
                'store__store_name', 'store_id'
            ).annotate(
                bonus_count=Sum('bonus_items'),
                discount_amount=Sum('discount_amount')
            ).order_by('-bonus_count')[:5]

        analytics_data = {
            'total_bonus_items': stats['total_bonus_items'] or 0,
            'total_discount': float(stats['total_discount'] or 0),
            'total_orders_with_bonus': stats['total_orders'] or 0,
            'total_products_with_bonus': stats['total_products'] or 0,
            'top_products': list(top_products),
            'top_stores': list(top_stores)
        }

        serializer = BonusAnalyticsSerializer(analytics_data)
        return Response(serializer.data)
