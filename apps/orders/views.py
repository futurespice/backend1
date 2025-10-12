from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import transaction
from .models import Order, OrderHistory, OrderReturn
from .serializers import OrderSerializer, OrderHistorySerializer, OrderReturnSerializer, CreateOrderSerializer, CreateOrderReturnSerializer
from .services import OrderService
from users.permissions import IsAdminUser, IsPartnerUser, IsStoreUser
from products.models import BonusHistory, DefectiveProduct
from .filters import OrderFilter
from rest_framework.exceptions import ValidationError
from decimal import Decimal


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrderFilter
    search_fields = ['store__name', 'partner__name']
    ordering_fields = ['created_at', 'total_amount']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ['confirm', 'reject']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return Order.objects.all()
        elif user.role == 'partner':
            return Order.objects.filter(partner=user)
        elif user.role == 'store':
            return Order.objects.filter(store__selections__user=user)
        return Order.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            store = serializer.validated_data['store']
            if store.approval_status != 'approved':
                return Response({'error': 'Магазин не одобрен'}, status=status.HTTP_403_FORBIDDEN)
            order = OrderService.create_order(
                store=store,
                partner=request.user,
                items_data=serializer.validated_data['items'],
                note=serializer.validated_data.get('note', ''),
                idempotency_key=serializer.validated_data['idempotency_key']
            )
            return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        order = self.get_object()
        idempotency_key = request.data.get('idempotency_key')
        try:
            OrderService.confirm_order(order, idempotency_key)
            return Response({'status': 'confirmed'})
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        order = self.get_object()
        if order.status != 'pending':
            return Response({'error': 'Заказ уже обработан'}, status=status.HTTP_400_BAD_REQUEST)
        order.status = 'rejected'
        order.save()
        return Response({'status': 'rejected'})

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        order = self.get_object()
        history = order.history.all()
        bonuses = BonusHistory.objects.filter(store=order.store, partner=order.partner)
        defects = DefectiveProduct.objects.filter(partner=order.partner)
        return Response({
            'history': OrderHistorySerializer(history, many=True).data,
            'bonuses': bonuses.values('product__name', 'bonus_count', 'date'),
            'defects': defects.values('product__name', 'quantity', 'amount', 'date')
        })

    @action(detail=True, methods=['get'])
    def diagram(self, request, pk=None):
        order = self.get_object()
        items = order.items.all()
        total = order.total_amount or Decimal('1')
        shares = {item.product.name: (item.total / total) for item in items}
        return Response({'shares': shares})


class OrderHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return OrderHistory.objects.all()
        elif user.role == 'partner':
            return OrderHistory.objects.filter(order__partner=user)
        elif user.role == 'store':
            return OrderHistory.objects.filter(order__store__selections__user=user)
        return OrderHistory.objects.none()


class OrderReturnViewSet(viewsets.ModelViewSet):
    serializer_class = OrderReturnSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['approve', 'reject']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated(), IsPartnerUser()]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return OrderReturn.objects.all()
        return OrderReturn.objects.filter(order__partner=user)

    def create(self, request, *args, **kwargs):
        serializer = CreateOrderReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            order = serializer.validated_data['order']
            order_return = OrderService.create_return(
                order=order,
                items_data=serializer.validated_data['items'],
                reason=serializer.validated_data.get('reason', ''),
                idempotency_key=serializer.validated_data['idempotency_key']
            )
            return Response(OrderReturnSerializer(order_return).data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        order_return = self.get_object()
        try:
            OrderService.approve_return(order_return)
            return Response({'status': 'approved'})
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        order_return = self.get_object()
        if order_return.status != 'pending':
            return Response({'error': 'Возврат уже обработан'}, status=status.HTTP_400_BAD_REQUEST)
        order_return.status = 'rejected'
        order_return.save()
        return Response({'status': 'rejected'})