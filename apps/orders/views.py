# apps/orders/views.py
"""
API для заказов: PartnerOrder, StoreOrder, OrderHistory, OrderReturn
Полная поддержка: CRUD, действия, фильтры, права, идемпотентность, уведомления
"""

from __future__ import annotations

import logging
from typing import Optional

from django.db import transaction
from django.db.models import Q, Prefetch
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend

from drf_spectacular.utils import extend_schema, OpenApiExample
from drf_spectacular.types import OpenApiTypes

from .models import (
    PartnerOrder, PartnerOrderItem,
    StoreOrder, StoreOrderItem,
    OrderHistory,
    OrderReturn, OrderReturnItem,
)
from .serializers import (
    PartnerOrderSerializer, CreatePartnerOrderSerializer,
    StoreOrderSerializer, CreateStoreOrderSerializer,
    OrderHistorySerializer,
    OrderReturnSerializer, CreateOrderReturnSerializer,
)
from .services import OrderService
from .filters import PartnerOrderFilter, StoreOrderFilter, OrderReturnFilter

from users.permissions import (
    IsAdminUser,
    IsPartnerUser,
    IsStoreUser,
)

from stores.models import StoreRequest, StoreSelection

logger = logging.getLogger('orders.views')


# =============================================================================
#  PARTNER ORDER VIEWSET
# =============================================================================

@extend_schema(tags=['Partner Orders'])
class PartnerOrderViewSet(viewsets.ModelViewSet):
    """
    Заказы партнёров → админу
    - GET: список (admin/partner)
    - POST: создать (partner)
    - POST /{id}/confirm/: подтвердить (admin)
    """
    queryset = PartnerOrder.objects.all()   # ✅ важно для router basename
    serializer_class = PartnerOrderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PartnerOrderFilter
    search_fields = ['partner__email', 'partner__first_name', 'partner__last_name', 'note']
    ordering_fields = ['id', 'created_at', 'total_amount', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        queryset = PartnerOrder.objects.select_related('partner').prefetch_related(
            Prefetch('items', queryset=PartnerOrderItem.objects.select_related('product'))
        )

        if user.role == 'admin':
            return queryset
        if user.role == 'partner':
            return queryset.filter(partner=user)

        return queryset.none()

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated(), IsPartnerUser()]
        if self.action in ['confirm', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]

    @extend_schema(
        request=CreatePartnerOrderSerializer,
        responses={201: PartnerOrderSerializer},
        examples=[
            OpenApiExample(
                'Пример создания',
                value={
                    "note": "Срочно",
                    "items": [
                        {"product": 1, "quantity": "2.5", "price": "150.00"}
                    ],
                    "idempotency_key": "partner-order-123"
                }
            )
        ]
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs) -> Response:
        """Создание заказа партнёра"""
        serializer = CreatePartnerOrderSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        try:
            order = OrderService.create_partner_order(
                partner=request.user,
                items_data=serializer.validated_data['items'],
                note=serializer.validated_data.get('note', ''),
                idempotency_key=serializer.validated_data.get('idempotency_key')
            )
            return Response(
                PartnerOrderSerializer(order, context=self.get_serializer_context()).data,
                status=status.HTTP_201_CREATED
            )
        except (ValidationError, DjangoValidationError) as e:
            logger.warning(f"Ошибка создания заказа партнёра: {str(e)}")
            raise ValidationError(detail=str(e))

    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        description="Подтверждение заказа админом"
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    @transaction.atomic
    def confirm(self, request, pk: Optional[int] = None) -> Response:
        """Подтверждение заказа партнёра"""
        order = self.get_object()

        try:
            OrderService.confirm_partner_order(order)
            return Response({'status': 'confirmed', 'order_id': order.id})
        except (ValidationError, DjangoValidationError) as e:
            logger.error(f"Ошибка подтверждения PartnerOrder #{order.id}: {str(e)}")
            raise ValidationError(detail=str(e))


# =============================================================================
#  STORE ORDER VIEWSET
# =============================================================================

@extend_schema(tags=['Store Orders'])
class StoreOrderViewSet(viewsets.ModelViewSet):
    """
    Заказы магазинов → партнёру
    - GET: список (admin/partner/store)
    - POST: создать из StoreRequest (partner)
    - POST /{id}/fulfill/: выполнить (partner)
    """
    queryset = StoreOrder.objects.all()    # ✅ важно для router basename
    serializer_class = StoreOrderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = StoreOrderFilter
    search_fields = ['store__name', 'partner__email', 'note']
    ordering_fields = ['id', 'created_at', 'total_amount', 'is_fulfilled']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        queryset = StoreOrder.objects.select_related(
            'store', 'partner', 'store_request'
        ).prefetch_related(
            Prefetch('items', queryset=StoreOrderItem.objects.select_related('product'))
        )

        if user.role == 'admin':
            return queryset
        if user.role == 'partner':
            return queryset.filter(partner=user)
        if user.role == 'store':
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

    @extend_schema(
        request=CreateStoreOrderSerializer,
        responses={201: StoreOrderSerializer}
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs) -> Response:
        """Создание заказа из StoreRequest"""
        serializer = CreateStoreOrderSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        try:
            # serializer может отдавать id или объект — поддержим оба варианта
            store_request_val = serializer.validated_data['store_request_id']
            if isinstance(store_request_val, StoreRequest):
                store_request = store_request_val
            else:
                store_request = get_object_or_404(StoreRequest, id=store_request_val)

            if store_request.status != 'confirmed':
                raise ValidationError("Запрос должен быть подтверждён")

            order = OrderService.create_store_order_from_request(
                store_request=store_request,
                partner=request.user,
                idempotency_key=serializer.validated_data.get('idempotency_key')
            )
            return Response(
                StoreOrderSerializer(order, context=self.get_serializer_context()).data,
                status=status.HTTP_201_CREATED
            )
        except (ValidationError, DjangoValidationError) as e:
            logger.warning(f"Ошибка создания заказа магазина: {str(e)}")
            raise ValidationError(detail=str(e))

    @extend_schema(description="Выполнение заказа партнёром")
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsPartnerUser])
    @transaction.atomic
    def fulfill(self, request, pk: Optional[int] = None) -> Response:
        """Выполнение заказа"""
        order = self.get_object()

        if order.partner != request.user:
            raise PermissionDenied("Вы не можете выполнить этот заказ")

        try:
            OrderService.fulfill_store_order(order)
            return Response({'status': 'fulfilled', 'order_id': order.id})
        except (ValidationError, DjangoValidationError) as e:
            logger.error(f"Ошибка выполнения StoreOrder #{order.id}: {str(e)}")
            raise ValidationError(detail=str(e))


# =============================================================================
#  ORDER HISTORY VIEWSET
# =============================================================================

@extend_schema(tags=['Order History'])
class OrderHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """История всех операций по заказам"""
    queryset = OrderHistory.objects.all()   # ✅ важно для router basename
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

        if user.role == 'partner':
            partner_orders = PartnerOrder.objects.filter(partner=user).values_list('id', flat=True)
            store_orders = StoreOrder.objects.filter(partner=user).values_list('id', flat=True)
            return queryset.filter(
                Q(order_type='partner', order_id__in=partner_orders) |
                Q(order_type='store', order_id__in=store_orders)
            )

        if user.role == 'store':
            try:
                selection = StoreSelection.objects.get(user=user)
                store_orders = StoreOrder.objects.filter(store=selection.store).values_list('id', flat=True)
                return queryset.filter(order_type='store', order_id__in=store_orders)
            except StoreSelection.DoesNotExist:
                return queryset.none()

        return queryset.none()


# =============================================================================
#  ORDER RETURN VIEWSET
# =============================================================================

@extend_schema(tags=['Order Returns'])
class OrderReturnViewSet(viewsets.ModelViewSet):
    """
    Возвраты товаров
    - GET: список
    - POST: создать (store)
    - POST /{id}/approve/: подтвердить (partner)
    - POST /{id}/reject/: отклонить (partner)
    """
    queryset = OrderReturn.objects.all()    # ✅ важно для router basename
    serializer_class = OrderReturnSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrderReturnFilter
    search_fields = ['order__store__name', 'reason']
    ordering_fields = ['id', 'created_at', 'total_amount', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        queryset = OrderReturn.objects.select_related(
            'order', 'order__store', 'order__partner'
        ).prefetch_related(
            Prefetch('items', queryset=OrderReturnItem.objects.select_related('product'))
        )

        if user.role == 'admin':
            return queryset
        if user.role == 'partner':
            return queryset.filter(order__partner=user)
        if user.role == 'store':
            try:
                selection = StoreSelection.objects.get(user=user)
                return queryset.filter(order__store=selection.store)
            except StoreSelection.DoesNotExist:
                return queryset.none()

        return queryset.none()

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated(), IsStoreUser()]
        if self.action in ['approve', 'reject']:
            return [IsAuthenticated(), IsPartnerUser()]
        return [IsAuthenticated()]

    @extend_schema(
        request=CreateOrderReturnSerializer,
        responses={201: OrderReturnSerializer}
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs) -> Response:
        """Создание возврата"""
        serializer = CreateOrderReturnSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        try:
            order_val = serializer.validated_data['order_id']
            # поддержим id или объект
            if hasattr(order_val, 'id'):
                order = order_val
            else:
                order = get_object_or_404(StoreOrder, id=order_val)

            selection = StoreSelection.objects.get(user=request.user)

            if order.store != selection.store:
                raise PermissionDenied("Вы не можете вернуть товары из чужого заказа")

            return_request = OrderService.create_return(
                order=order,
                items_data=serializer.validated_data['items'],
                reason=serializer.validated_data['reason'],
                idempotency_key=serializer.validated_data.get('idempotency_key')
            )
            return Response(
                OrderReturnSerializer(return_request, context=self.get_serializer_context()).data,
                status=status.HTTP_201_CREATED
            )
        except (ValidationError, DjangoValidationError) as e:
            logger.warning(f"Ошибка создания возврата: {str(e)}")
            raise ValidationError(detail=str(e))

    @extend_schema(description="Подтверждение возврата")
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsPartnerUser])
    @transaction.atomic
    def approve(self, request, pk: Optional[int] = None) -> Response:
        return_request = self.get_object()

        if return_request.order.partner != request.user:
            raise PermissionDenied("Вы не можете подтвердить этот возврат")

        try:
            OrderService.approve_return(return_request)
            return Response({'status': 'approved', 'return_id': return_request.id})
        except (ValidationError, DjangoValidationError) as e:
            logger.error(f"Ошибка подтверждения возврата #{return_request.id}: {str(e)}")
            raise ValidationError(detail=str(e))

    @extend_schema(description="Отклонение возврата")
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsPartnerUser])
    @transaction.atomic
    def reject(self, request, pk: Optional[int] = None) -> Response:
        return_request = self.get_object()

        if return_request.order.partner != request.user:
            raise PermissionDenied("Вы не можете отклонить этот возврат")

        if return_request.status != 'pending':
            raise ValidationError("Возврат уже обработан")

        return_request.status = 'rejected'
        return_request.save(update_fields=['status'])

        return Response({'status': 'rejected', 'return_id': return_request.id})
