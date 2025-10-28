from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from .models import Order, OrderHistory, OrderReturn
from .serializers import OrderSerializer, OrderHistorySerializer, OrderReturnSerializer, CreateOrderSerializer, CreateOrderReturnSerializer
from .services import OrderService
from users.permissions import IsAdminUser, IsPartnerUser, IsStoreUser
from products.models import BonusHistory, DefectiveProduct
from .filters import OrderFilter
from rest_framework.exceptions import ValidationError
from django.db import IntegrityError
import logging
logger = logging.getLogger(__name__)


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
        qs = Order.objects.select_related('store', 'partner').prefetch_related('items__product')
        user = self.request.user
        if user.role == 'admin':
            return qs
        if user.role == 'partner':
            return qs.filter(partner=user)
        if user.role == 'store':
            return qs.filter(store__selections__user=user)
        return qs.none()

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.status == Order.Status.PENDING:
            obj.status = Order.Status.REJECTED
            obj.save(update_fields=["status"])
            return Response({"status": "rejected"})
        return Response({"detail": "Нельзя удалить подтвержденный заказ"}, status=400)

    @extend_schema(
        request=CreateOrderSerializer,
        responses={
            201: OpenApiResponse(response=OrderSerializer, description="Заказ создан"),
            400: OpenApiResponse(description="Валидационная ошибка"),
            403: OpenApiResponse(description="Магазин не одобрен"),
            409: OpenApiResponse(description="Дубликат idempotency_key"),
        },
        examples=[
            OpenApiExample(
                "Пример запроса (минимально необходимый)",
                value={
                    "store": 12,
                    "note": "Доставить утром",
                    "idempotency_key": "6b2f9f4e-8a03-4d1b-9e18-c8d3d9e5df00",
                    "items": [
                        {"product": 101, "quantity": 5},
                        {"product": 305, "quantity": 2}
                    ]
                },
                request_only=True
            ),
            OpenApiExample(
                "Пример ответа (201)",
                value={
                    "id": 987,
                    "store": {"id": 12, "name": "ТОО Алма"},
                    "partner": {"id": 3, "email": "partner@example.com"},
                    "status": "pending",
                    "total_amount": "15450.00",
                    "note": "Доставить утром",
                    "created_at": "2025-10-28T14:22:11Z",
                    "items": [
                        {
                            "product": {"id": 101, "name": "Мука 2кг"},
                            "quantity": 5,
                            "unit_price": "1200.00",
                            "total": "6000.00"
                        },
                        {
                            "product": {"id": 305, "name": "Сахар 1кг"},
                            "quantity": 2,
                            "unit_price": "4700.00",
                            "total": "9400.00"
                        }
                    ]
                },
                response_only=True
            ),
            OpenApiExample(
                "Ошибка 409: дубликат idempotency_key",
                value={"error": "Duplicate or invalid data (idempotency_key?)"},
                response_only=True,
                status_codes=[str(status.HTTP_409_CONFLICT)]
            ),
        ],
    )
    def create(self, request, *args, **kwargs):
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            store = serializer.validated_data['store']
            if store.approval_status != 'approved':
                return Response({'error': 'Магазин не одобрен'}, status=status.HTTP_403_FORBIDDEN)

            # ✅ ИСПРАВЛЕНИЕ: Преобразуем items в формат с ID
            items_data = []
            for item in serializer.validated_data['items']:
                product = item['product']
                # Если product - объект, берём его ID
                product_id = product.id if hasattr(product, 'id') else product
                items_data.append({
                    'product': product_id,
                    'quantity': item['quantity']
                })

            order = OrderService.create_order(
                store=store,
                partner=request.user,
                items_data=items_data,  # Теперь передаём правильный формат
                note=serializer.validated_data.get('note', ''),
                idempotency_key=serializer.validated_data['idempotency_key']
            )
            return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as e:
            logger.warning("IntegrityError on order create: %s", e, exc_info=True)
            return Response({'error': 'Duplicate or invalid data (idempotency_key?)'}, status=status.HTTP_409_CONFLICT)


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
        total = float(order.total_amount or 0) or 1.0
        shares = {it.product.name: float(it.total) / total for it in order.items.all()}
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

            # ✅ ИСПРАВЛЕНИЕ: Преобразуем items в формат с ID
            items_data = []
            for item in serializer.validated_data['items']:
                product = item['product']
                product_id = product.id if hasattr(product, 'id') else product
                items_data.append({
                    'product': product_id,
                    'quantity': item['quantity']
                })

            order_return = OrderService.create_return(
                order=order,
                items_data=items_data,  # Теперь передаём правильный формат
                reason=serializer.validated_data.get('reason', ''),
                idempotency_key=serializer.validated_data['idempotency_key']
            )
            return Response(OrderReturnSerializer(order_return).data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as e:
            logger.warning("IntegrityError on order return create: %s", e, exc_info=True)
            return Response({'error': 'Duplicate or invalid data (idempotency_key?)'}, status=status.HTTP_409_CONFLICT)


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