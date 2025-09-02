from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.utils import timezone
from datetime import timedelta

from .models import Store
from .serializers import (
    StoreListSerializer, StoreDetailSerializer, StoreCreateUpdateSerializer,
    StoreAssignUserSerializer, StoreStatisticsSerializer
)
from .filters import StoreFilter
from users.permissions import IsAdminUser, IsPartnerUser, IsStoreUser


class StoreViewSet(viewsets.ModelViewSet):
    """API магазинов"""
    queryset = Store.objects.select_related('owner', 'user', 'region', 'city')
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = StoreFilter
    search_fields = ['name', 'inn', 'phone', 'contact_name', 'owner__email']
    ordering_fields = ['name', 'created_at', 'is_active']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return StoreListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return StoreCreateUpdateSerializer
        return StoreDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # Партнеры видят только свои магазины
        if user.role == 'partner':
            queryset = queryset.filter(owner=user)
        # Пользователи-магазины видят только свой магазин
        elif user.role == 'store':
            queryset = queryset.filter(user=user)
        # Админы видят все магазины

        return queryset

    def get_permissions(self):
        """Разные права для разных действий"""
        if self.action in ['create']:
            permission_classes = [IsPartnerUser | IsAdminUser]
        elif self.action in ['update', 'partial_update']:
            permission_classes = [IsPartnerUser | IsAdminUser]
        elif self.action in ['destroy']:
            permission_classes = [IsAdminUser]
        else:
            permission_classes = [permissions.IsAuthenticated]

        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Автоматически назначаем владельца при создании"""
        if self.request.user.role == 'partner':
            serializer.save(owner=self.request.user)
        else:
            # Админ должен явно указать владельца
            serializer.save()

    @action(detail=True, methods=['post'], permission_classes=[IsPartnerUser | IsAdminUser])
    def assign_user(self, request, pk=None):
        """Назначить пользователя магазину"""
        store = self.get_object()
        serializer = StoreAssignUserSerializer(data=request.data)

        if serializer.is_valid():
            from django.contrib.auth import get_user_model
            User = get_user_model()

            user = User.objects.get(id=serializer.validated_data['user_id'])
            store.user = user
            store.save()

            return Response({
                'message': f'Пользователь {user.full_name} назначен магазину {store.name}',
                'store_id': store.id,
                'user_id': user.id,
                'user_name': user.full_name
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[IsPartnerUser | IsAdminUser])
    def unassign_user(self, request, pk=None):
        """Отвязать пользователя от магазина"""
        store = self.get_object()

        if not store.user:
            return Response({'error': 'К магазину не привязан пользователь'}, status=status.HTTP_400_BAD_REQUEST)

        user_name = store.user.full_name
        store.user = None
        store.save()

        return Response({
            'message': f'Пользователь {user_name} отвязан от магазина {store.name}'
        })

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def toggle_active(self, request, pk=None):
        """Активировать/деактивировать магазин"""
        store = self.get_object()
        store.is_active = not store.is_active
        store.save()

        status_text = 'активирован' if store.is_active else 'деактивирован'
        return Response({
            'message': f'Магазин {store.name} {status_text}',
            'is_active': store.is_active
        })

    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Статистика магазина"""
        store = self.get_object()

        # Период (по умолчанию - текущий месяц)
        period_start = request.query_params.get('start_date')
        period_end = request.query_params.get('end_date')

        if not period_start:
            now = timezone.now()
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            period_start = timezone.datetime.fromisoformat(period_start)

        if not period_end:
            period_end = timezone.now()
        else:
            period_end = timezone.datetime.fromisoformat(period_end)

        # Заказы
        orders = store.orders.filter(
            order_date__range=[period_start, period_end],
            status__in=['confirmed', 'completed']
        )

        total_orders = orders.count()
        total_orders_amount = sum(order.total_amount for order in orders)
        avg_order_amount = total_orders_amount / total_orders if total_orders > 0 else 0

        # Долги
        debts = store.debts.filter(created_at__range=[period_start, period_end])
        total_debt = sum(debt.amount for debt in debts)
        unpaid_debt = sum(debt.amount for debt in debts if not debt.is_paid)

        # Бонусы
        bonus_counter = getattr(store, 'bonus_counter', None)
        if bonus_counter:
            bonus_transactions = store.bonus_transactions.filter(
                created_at__range=[period_start, period_end],
                transaction_type='earned'
            )
            bonus_items_received = sum(t.quantity for t in bonus_transactions)
            bonus_amount_saved = sum(t.amount_saved for t in bonus_transactions)
        else:
            bonus_items_received = 0
            bonus_amount_saved = 0

        data = {
            'store_id': store.id,
            'store_name': store.name,
            'total_orders': total_orders,
            'total_orders_amount': total_orders_amount,
            'avg_order_amount': avg_order_amount,
            'total_debt': total_debt,
            'unpaid_debt': unpaid_debt,
            'bonus_items_received': bonus_items_received,
            'bonus_amount_saved': bonus_amount_saved,
            'period_start': period_start,
            'period_end': period_end
        }

        serializer = StoreStatisticsSerializer(data)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def with_debt(self, request):
        """Магазины с долгами"""
        stores_with_debt = []

        for store in self.get_queryset():
            debt_amount = store.get_debt_amount()
            if debt_amount > 0:
                stores_with_debt.append(store)

        # Сортируем по убыванию долга
        stores_with_debt.sort(key=lambda s: s.get_debt_amount(), reverse=True)

        page = self.paginate_queryset(stores_with_debt)
        if page is not None:
            serializer = StoreListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = StoreListSerializer(stores_with_debt, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def inactive(self, request):
        """Неактивные магазины"""
        inactive_stores = self.get_queryset().filter(is_active=False)

        page = self.paginate_queryset(inactive_stores)
        if page is not None:
            serializer = StoreListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = StoreListSerializer(inactive_stores, many=True, context={'request': request})
        return Response(serializer.data)