from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import transaction, models
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

from .models import (
    PartnerOrder, StoreOrder, OrderHistory, OrderReturn
)
from .serializers import (
    PartnerOrderSerializer, CreatePartnerOrderSerializer,
    StoreOrderSerializer, CreateStoreOrderSerializer,
    OrderHistorySerializer,
    OrderReturnSerializer, CreateOrderReturnSerializer
)
from .services import OrderService
from .filters import PartnerOrderFilter, StoreOrderFilter, OrderReturnFilter
from users.permissions import IsAdminUser, IsPartnerUser, IsStoreUser
from stores.models import StoreRequest


class PartnerOrderViewSet(viewsets.ModelViewSet):
    """
    Заказы партнёров → админу
    GET /partner-orders/ - список
    POST /partner-orders/ - создать
    POST /partner-orders/{id}/confirm/ - подтвердить (admin)
    """
    serializer_class = PartnerOrderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PartnerOrderFilter
    search_fields = ['partner__name', 'note']
    ordering_fields = ['created_at', 'total_amount']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        queryset = PartnerOrder.objects.select_related('partner').prefetch_related('items__product')

        if user.role == 'admin':
            return queryset
        elif user.role == 'partner':
            return queryset.filter(partner=user)

        return queryset.none()

    def get_permissions(self):
        if self.action in ['create']:
            return [IsAuthenticated(), IsPartnerUser()]
        elif self.action in ['confirm', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Создание заказа партнёра"""
        serializer = CreatePartnerOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            order = OrderService.create_partner_order(
                partner=request.user,
                items_data=serializer.validated_data['items'],
                note=serializer.validated_data.get('note', ''),
                idempotency_key=serializer.validated_data.get('idempotency_key')
            )
            return Response(
                PartnerOrderSerializer(order).data,
                status=status.HTTP_201_CREATED
            )
        except (ValidationError, DjangoValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    @transaction.atomic
    def confirm(self, request, pk=None):
        """Подтверждение заказа партнёра админом"""
        order = self.get_object()

        try:
            OrderService.confirm_partner_order(order)
            return Response({'status': 'confirmed'})
        except (ValidationError, DjangoValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StoreOrderViewSet(viewsets.ModelViewSet):
    """
    Заказы магазинов → партнёру
    GET /store-orders/ - список
    POST /store-orders/ - создать из StoreRequest
    POST /store-orders/{id}/fulfill/ - выполнить (partner)
    """
    serializer_class = StoreOrderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = StoreOrderFilter
    search_fields = ['store__name', 'partner__name', 'note']
    ordering_fields = ['created_at', 'total_amount']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        queryset = StoreOrder.objects.select_related(
            'store', 'partner', 'store_request'
        ).prefetch_related('items__product')

        if user.role == 'admin':
            return queryset
        elif user.role == 'partner':
            return queryset.filter(partner=user)
        elif user.role == 'store':
            from stores.models import StoreSelection
            try:
                selection = StoreSelection.objects.get(user=user)
                return queryset.filter(store=selection.store)
            except StoreSelection.DoesNotExist:
                return queryset.none()

        return queryset.none()

    def get_permissions(self):
        if self.action in ['create', 'fulfill']:
            return [IsAuthenticated(), IsPartnerUser()]
        return [IsAuthenticated()]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Создание заказа магазина из StoreRequest"""
        serializer = CreateStoreOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            store_request = StoreRequest.objects.get(
                id=serializer.validated_data['store_request_id']
            )

            order = OrderService.create_store_order_from_request(
                store_request=store_request,
                partner=request.user,
                idempotency_key=serializer.validated_data.get('idempotency_key')
            )

            return Response(
                StoreOrderSerializer(order).data,
                status=status.HTTP_201_CREATED
            )
        except (ValidationError, DjangoValidationError, StoreRequest.DoesNotExist) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsPartnerUser])
    @transaction.atomic
    def fulfill(self, request, pk=None):
        """Выполнение заказа магазина"""
        order = self.get_object()

        # Проверка что партнёр может выполнить этот заказ
        if order.partner != request.user:
            return Response(
                {'error': 'Вы не можете выполнить этот заказ'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            OrderService.fulfill_store_order(order)
            return Response({'status': 'fulfilled'})
        except (ValidationError, DjangoValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class OrderHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """История заказов (только чтение)"""
    serializer_class = OrderHistorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['order_type', 'type']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        queryset = OrderHistory.objects.select_related('product')

        if user.role == 'admin':
            return queryset
        elif user.role == 'partner':
            # Партнёр видит историю своих заказов
            partner_order_ids = PartnerOrder.objects.filter(partner=user).values_list('id', flat=True)
            store_order_ids = StoreOrder.objects.filter(partner=user).values_list('id', flat=True)

            return queryset.filter(
                (models.Q(order_type='partner', order_id__in=partner_order_ids) |
                 models.Q(order_type='store', order_id__in=store_order_ids))
            )
        elif user.role == 'store':
            from stores.models import StoreSelection
            try:
                selection = StoreSelection.objects.get(user=user)
                store_order_ids = StoreOrder.objects.filter(store=selection.store).values_list('id', flat=True)
                return queryset.filter(order_type='store', order_id__in=store_order_ids)
            except StoreSelection.DoesNotExist:
                return queryset.none()

        return queryset.none()


class OrderReturnViewSet(viewsets.ModelViewSet):
    """
    Возвраты товаров
    GET /order-returns/ - список
    POST /order-returns/ - создать
    POST /order-returns/{id}/approve/ - подтвердить (admin/partner)
    POST /order-returns/{id}/reject/ - отклонить
    """
    serializer_class = OrderReturnSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrderReturnFilter
    search_fields = ['order__store__name', 'reason']
    ordering_fields = ['created_at', 'total_amount']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        queryset = OrderReturn.objects.select_related('order', 'order__store').prefetch_related('items__product')

        if user.role == 'admin':
            return queryset
        elif user.role == 'partner':
            return queryset.filter(order__partner=user)
        elif user.role == 'store':
            from stores.models import StoreSelection
            try:
                selection = StoreSelection.objects.get(user=user)
                return queryset.filter(order__store=selection.store)
            except StoreSelection.DoesNotExist:
                return queryset.none()

        return queryset.none()

    def get_permissions(self):
        if self.action in ['create']:
            return [IsAuthenticated(), IsStoreUser()]
        elif self.action in ['approve', 'reject']:
            return [IsAuthenticated(), IsPartnerUser()]
        return [IsAuthenticated()]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Создание возврата"""
        serializer = CreateOrderReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            order = StoreOrder.objects.get(id=serializer.validated_data['order_id'])

            # Проверка что магазин может создать возврат для этого заказа
            from stores.models import StoreSelection
            selection = StoreSelection.objects.get(user=request.user)

            if order.store != selection.store:
                return Response(
                    {'error': 'Вы не можете создать возврат для этого заказа'},
                    status=status.HTTP_403_FORBIDDEN
                )

            order_return = OrderService.create_return(
                order=order,
                items_data=serializer.validated_data['items'],
                reason=serializer.validated_data['reason'],
                idempotency_key=serializer.validated_data.get('idempotency_key')
            )

            return Response(
                OrderReturnSerializer(order_return).data,
                status=status.HTTP_201_CREATED
            )
        except (ValidationError, DjangoValidationError, StoreOrder.DoesNotExist) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsPartnerUser])
    @transaction.atomic
    def approve(self, request, pk=None):
        """Подтверждение возврата"""
        order_return = self.get_object()

        # Проверка что партнёр может подтвердить этот возврат
        if order_return.order.partner != request.user:
            return Response(
                {'error': 'Вы не можете подтвердить этот возврат'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            OrderService.approve_return(order_return)
            return Response({'status': 'approved'})
        except (ValidationError, DjangoValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsPartnerUser])
    @transaction.atomic
    def reject(self, request, pk=None):
        """Отклонение возврата"""
        order_return = self.get_object()

        if order_return.order.partner != request.user:
            return Response(
                {'error': 'Вы не можете отклонить этот возврат'},
                status=status.HTTP_403_FORBIDDEN
            )

        if order_return.status != 'pending':
            return Response(
                {'error': 'Возврат уже обработан'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order_return.status = 'rejected'
        order_return.save()

        return Response({'status': 'rejected'})