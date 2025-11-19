# apps/orders/views.py

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .filters import OrderReturnFilter, PartnerOrderFilter, StoreOrderFilter
from .models import (
    OrderHistory,
    OrderReturn,
    PartnerOrder,
    StoreOrder,
)
from .permissions import IsAdminOrPartner
from .serializers import (
    OrderHistorySerializer,
    OrderReturnSerializer,
    PartnerOrderSerializer,
    StoreOrderSerializer,
)
from .services import OrderService


class PartnerOrderViewSet(viewsets.ModelViewSet):
    """
    Заказы партнёров.

    - admin видит все
    - partner — только свои
    """

    queryset = PartnerOrder.objects.all().select_related("partner")
    serializer_class = PartnerOrderSerializer
    filterset_class = PartnerOrderFilter
    permission_classes = [IsAdminOrPartner]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        if getattr(user, "role", None) == "admin" or user.is_superuser:
            return qs
        if getattr(user, "role", None) == "partner":
            return qs.filter(partner=user)
        return qs.none()


class StoreOrderViewSet(viewsets.ModelViewSet):
    """
    Заказы магазинов.

    - admin видит все
    - partner — только свои (как партнёр)
    - store — только по своим магазинам (через StoreSelection)
    """

    queryset = (
        StoreOrder.objects.all()
        .select_related("store", "partner", "store__city", "store__region")
        .prefetch_related("items")
    )
    serializer_class = StoreOrderSerializer
    filterset_class = StoreOrderFilter

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        role = getattr(user, "role", None)
        if role == "admin" or user.is_superuser:
            return qs
        if role == "partner":
            return qs.filter(partner=user)
        if role == "store":
            from stores.models import StoreSelection

            store_ids = (
                StoreSelection.objects.filter(user=user)
                .values_list("store_id", flat=True)
                .distinct()
            )
            return qs.filter(store_id__in=store_ids)
        return qs.none()

    @action(detail=True, methods=["post"], url_path="change-status")
    def change_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get("status")
        if not new_status:
            return Response(
                {"detail": "Не указан новый статус"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order = OrderService.change_store_order_status(
            order=order,
            new_status=new_status,
            changed_by=request.user,
            comment=request.data.get("comment", ""),
        )
        return Response(self.get_serializer(order).data)


class OrderReturnViewSet(viewsets.ModelViewSet):
    """
    Возвраты по заказам.

    - admin видит все
    - partner — только свои
    - store — только по своим магазинам
    """

    queryset = (
        OrderReturn.objects.all()
        .select_related("store", "partner", "order")
        .prefetch_related("items")
    )
    serializer_class = OrderReturnSerializer
    filterset_class = OrderReturnFilter

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        role = getattr(user, "role", None)
        if role == "admin" or user.is_superuser:
            return qs
        if role == "partner":
            return qs.filter(partner=user)
        if role == "store":
            from stores.models import StoreSelection

            store_ids = (
                StoreSelection.objects.filter(user=user)
                .values_list("store_id", flat=True)
                .distinct()
            )
            return qs.filter(store_id__in=store_ids)
        return qs.none()

    @action(detail=True, methods=["post"], url_path="change-status")
    def change_status(self, request, pk=None):
        order_return = self.get_object()
        new_status = request.data.get("status")
        if not new_status:
            return Response(
                {"detail": "Не указан новый статус"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order_return = OrderService.change_order_return_status(
            order_return=order_return,
            new_status=new_status,
            changed_by=request.user,
            comment=request.data.get("comment", ""),
        )
        return Response(self.get_serializer(order_return).data)


class OrderHistoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Только чтение истории заказов.
    """

    queryset = OrderHistory.objects.all().select_related("changed_by", "product")
    serializer_class = OrderHistorySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        role = getattr(user, "role", None)
        if role == "admin" or user.is_superuser:
            return qs
        # для партнёра/магазина можно фильтровать по связям, но тут оставляем общий read
        return qs
