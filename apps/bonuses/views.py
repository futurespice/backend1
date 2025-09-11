from rest_framework import viewsets, permissions, status, generics
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import Sum, Count, Q
from datetime import datetime

from .models import BonusRule, BonusHistory, BonusCalculation
from .serializers import (
    BonusRuleSerializer, BonusHistorySerializer,
    BonusCalculationSerializer, BonusAnalyticsSerializer
)
from users.permissions import IsAdminUser


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
        'store', 'store__user', 'product', 'order'
    )
    serializer_class = BonusHistorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['store', 'product', 'order']
    search_fields = ['store__store_name', 'product__name']
    ordering_fields = ['created_at', 'bonus_discount']
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

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Сводка по бонусам"""
        qs = self.get_queryset()

        # Фильтры
        store_id = request.query_params.get('store')
        if store_id:
            qs = qs.filter(store_id=store_id)

        date_from = request.query_params.get('date_from')
        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                qs = qs.filter(created_at__date__gte=date_from)
            except ValueError:
                pass

        date_to = request.query_params.get('date_to')
        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                qs = qs.filter(created_at__date__lte=date_to)
            except ValueError:
                pass

        # Агрегация
        summary = qs.aggregate(
            total_bonus_discount=Sum('bonus_discount'),
            total_bonus_quantity=Sum('bonus_quantity'),
            total_records=Count('id')
        )

        return Response({
            'total_bonus_discount': summary['total_bonus_discount'] or 0,
            'total_bonus_quantity': summary['total_bonus_quantity'] or 0,
            'total_records': summary['total_records'] or 0
        })


class BonusCalculationView(generics.GenericAPIView):
    """Расчёт бонусов для товаров"""

    serializer_class = BonusCalculationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        Рассчитать бонусы для товаров

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

        # Валидация данных
        serializer = self.get_serializer(data=items, many=True)
        serializer.is_valid(raise_exception=True)

        # Получаем магазин
        try:
            store = request.user.store_profile
        except:
            return Response(
                {'error': 'Пользователь не является магазином'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from apps.products.models import Product

        calculator = BonusCalculation()
        results = []
        total_bonus_discount = 0

        for item in serializer.validated_data:
            try:
                product = Product.objects.get(id=item['product_id'])
                quantity = item['quantity']

                bonus_info = calculator.preview_bonus(store, product, quantity)

                result = {
                    'product_id': product.id,
                    'product_name': product.name,
                    'quantity': quantity,
                    'unit_price': product.price,
                    'bonus_quantity': bonus_info['bonus_quantity'],
                    'bonus_discount': bonus_info['bonus_discount'],
                    'new_cumulative': bonus_info['new_cumulative']
                }
                results.append(result)
                total_bonus_discount += bonus_info['bonus_discount']

            except Product.DoesNotExist:
                continue

        return Response({
            'items': results,
            'total_bonus_discount': total_bonus_discount
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
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        qs = BonusHistory.objects.all()
        user = request.user

        # Фильтрация по правам доступа
        if user.role == 'store':
            qs = qs.filter(store__user=user)
        elif user.role == 'partner':
            qs = qs.filter(store__partner=user)

        # Применяем фильтры
        filters = serializer.validated_data

        if filters.get('store_id'):
            qs = qs.filter(store_id=filters['store_id'])

        if filters.get('product_id'):
            qs = qs.filter(product_id=filters['product_id'])

        if filters.get('date_from'):
            qs = qs.filter(created_at__date__gte=filters['date_from'])

        if filters.get('date_to'):
            qs = qs.filter(created_at__date__lte=filters['date_to'])

        # Общая статистика
        total_stats = qs.aggregate(
            total_bonus_discount=Sum('bonus_discount'),
            total_bonus_quantity=Sum('bonus_quantity'),
            total_records=Count('id')
        )

        # Статистика по товарам
        product_stats = qs.values(
            'product__name', 'product_id'
        ).annotate(
            bonus_discount=Sum('bonus_discount'),
            bonus_quantity=Sum('bonus_quantity'),
            records_count=Count('id')
        ).order_by('-bonus_discount')[:10]

        # Статистика по магазинам (только для админов и партнёров)
        store_stats = []
        if user.role in ['admin', 'partner']:
            store_stats = qs.values(
                'store__store_name', 'store_id'
            ).annotate(
                bonus_discount=Sum('bonus_discount'),
                bonus_quantity=Sum('bonus_quantity'),
                records_count=Count('id')
            ).order_by('-bonus_discount')[:10]

        return Response({
            'total_stats': {
                'total_bonus_discount': total_stats['total_bonus_discount'] or 0,
                'total_bonus_quantity': total_stats['total_bonus_quantity'] or 0,
                'total_records': total_stats['total_records'] or 0
            },
            'top_products': list(product_stats),
            'top_stores': list(store_stats)
        })