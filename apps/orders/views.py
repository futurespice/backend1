from rest_framework import viewsets, permissions, status, generics, serializers
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import Q
from drf_spectacular.utils import extend_schema

from .models import Order, OrderItem, ProductRequest, ProductRequestItem
from .serializers import (
    OrderSerializer, OrderCreateSerializer, OrderItemSerializer,
    ProductRequestSerializer, ProductRequestCreateSerializer
)
from users.permissions import IsAdminUser, IsPartnerUser, IsStoreUser


class OrderViewSet(viewsets.ModelViewSet):
    """ViewSet для заказов"""

    queryset = Order.objects.select_related('store', 'store__partner').prefetch_related( 'items')  # исправили select_related
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'store']  # убрали partner
    search_fields = ['notes', 'store__store_name']
    ordering_fields = ['order_date', 'total_amount']
    ordering = ['-order_date']

    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        return OrderSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsStoreUser()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.role == 'store':
                # Магазин видит только свои заказы
            qs = qs.filter(store__user=user)
        elif user.role == 'partner':
                # Партнёр видит заказы своих магазинов
            qs = qs.filter(store__partner=user)  # исправили путь

        return qs

    @action(detail=True, methods=['post'], permission_classes=[IsPartnerUser])
    def confirm(self, request, pk=None):
        order = self.get_object()

            # Проверяем права
        if request.user.role == 'partner' and order.store.partner != request.user:  # исправили путь
            return Response(
                {'error': 'Нет прав на подтверждение этого заказа'},
                status=status.HTTP_403_FORBIDDEN
            )

        if order.status != 'pending':
             return Response(
                {'error': 'Можно подтвердить только заказы в статусе "Ожидает"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.confirm()
        serializer = self.get_serializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsPartnerUser])
    def complete(self, request, pk=None):
        """Завершить заказ (только партнёр)"""
        order = self.get_object()

        if order.status != 'confirmed':
            return Response(
                {'error': 'Можно завершить только подтверждённые заказы'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if order.partner != request.user:
            return Response(
                {'error': 'Вы можете завершать только свои заказы'},
                status=status.HTTP_403_FORBIDDEN
            )

        order.complete()
        serializer = self.get_serializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Отменить заказ"""
        order = self.get_object()

        if order.status not in ['pending', 'confirmed']:
            return Response(
                {'error': 'Можно отменить только активные заказы'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Проверяем права
        if request.user.role == 'store' and order.store.user != request.user:
            return Response(
                {'error': 'Нет прав на отмену этого заказа'},
                status=status.HTTP_403_FORBIDDEN
            )
        elif request.user.role == 'partner' and order.partner != request.user:
            return Response(
                {'error': 'Нет прав на отмену этого заказа'},
                status=status.HTTP_403_FORBIDDEN
            )

        order.cancel()
        serializer = self.get_serializer(order)
        return Response(serializer.data)


class OrderItemViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для позиций заказов (только чтение)"""

    queryset = OrderItem.objects.select_related('order', 'product')
    serializer_class = OrderItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['order', 'product']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.role == 'store':
            qs = qs.filter(order__store__user=user)
        elif user.role == 'partner':
            qs = qs.filter(order__partner=user)

        return qs


class ProductRequestViewSet(viewsets.ModelViewSet):
    """ViewSet для запросов товаров"""

    queryset = ProductRequest.objects.select_related('partner').prefetch_related('items')
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'partner']
    search_fields = ['partner_notes', 'admin_notes']
    ordering_fields = ['requested_at']
    ordering = ['-requested_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return ProductRequestCreateSerializer
        return ProductRequestSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsPartnerUser()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.role == 'partner':
            # Партнёр видит только свои запросы
            qs = qs.filter(partner=user)

        return qs

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        """Одобрить запрос товаров"""
        product_request = self.get_object()

        if product_request.status != 'pending':
            return Response(
                {'error': 'Можно одобрить только запросы в статусе "Ожидает рассмотрения"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        product_request.approve(request.user)
        serializer = self.get_serializer(product_request)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def reject(self, request, pk=None):
        """Отклонить запрос товаров"""
        product_request = self.get_object()

        if product_request.status != 'pending':
            return Response(
                {'error': 'Можно отклонить только запросы в статусе "Ожидает рассмотрения"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason', '')
        product_request.reject(request.user, reason)
        serializer = self.get_serializer(product_request)
        return Response(serializer.data)


class OrderCreateView(generics.CreateAPIView):
    """Создание заказа магазином"""

    serializer_class = OrderCreateSerializer
    permission_classes = [IsStoreUser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        # Возвращаем полные данные заказа
        response_serializer = OrderSerializer(order)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class BonusCalculationView(generics.GenericAPIView):
    """Предварительный расчёт бонусов"""
    permission_classes = [IsStoreUser]

    @extend_schema(
        operation_id="order_bonus_calculation",
        tags=["Orders"],
        request=None,
        responses={200: {"description": "Расчет бонусов"}}
    )

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

        from bonuses.models import BonusCalculator
        from products.models import Product

        calculator = BonusCalculator()
        results = []
        total_bonus_discount = 0

        for item in items:
            try:
                product = Product.objects.get(id=item['product_id'])
                quantity = float(item['quantity'])

                bonus_info = calculator.preview_bonus(store, product, quantity)

                result = {
                    'product_id': product.id,
                    'product_name': product.name,
                    'quantity': quantity,
                    'unit_price': product.price,
                    'bonus_quantity': bonus_info['bonus_quantity'],
                    'bonus_discount': bonus_info['bonus_discount']
                }
                results.append(result)
                total_bonus_discount += bonus_info['bonus_discount']

            except Product.DoesNotExist:
                continue
            except (ValueError, KeyError):
                continue

        return Response({
            'items': results,
            'total_bonus_discount': total_bonus_discount
        })