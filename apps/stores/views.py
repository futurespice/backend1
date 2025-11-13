# apps/stores/views.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import Q, Sum, F
from django.db import transaction
from decimal import Decimal
from datetime import datetime
import uuid
from django.core.exceptions import ValidationError

from products.serializers import BonusHistorySerializer, DefectiveProductSerializer
from .models import (
    Region, City, Store, StoreSelection,
    StoreProductRequest, StoreRequest, StoreRequestItem,
    StoreInventory, PartnerInventory, ReturnRequest, ReturnRequestItem
)
from .serializers import (
    RegionSerializer, CitySerializer, StoreSerializer, StoreSelectionSerializer,
    StoreProductRequestSerializer, CreateStoreRequestSerializer,
    StoreRequestSerializer, StoreInventorySerializer,
    PartnerInventorySerializer, ReturnRequestSerializer
)
from .services import StoreRequestService, InventoryService
from users.permissions import IsAdminUser, IsPartnerUser, IsStoreUser
from products.models import Product, BonusHistory, DefectiveProduct
from .filters import StoreFilter


# ИСПРАВЛЕНИЕ #4: Добавлен ViewSet для городов
class RegionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Регионы
    GET /regions/ - список регионов
    GET /regions/{id}/ - детали региона
    """
    queryset = Region.objects.all().prefetch_related('cities')
    serializer_class = RegionSerializer
    permission_classes = [IsAuthenticated]


class CityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ИСПРАВЛЕНИЕ #4: Города с фильтрацией по регионам
    GET /cities/ - все города
    GET /cities/?region={region_id} - города региона
    """
    queryset = City.objects.select_related('region')
    serializer_class = CitySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['region']
    search_fields = ['name']


class StoreViewSet(viewsets.ModelViewSet):
    """
    Магазины (CRUD)
    ИСПРАВЛЕНИЕ #2: Проверка роли при создании
    """
    queryset = Store.objects.select_related('region', 'city', 'created_by')
    serializer_class = StoreSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = StoreFilter
    search_fields = ['name', 'inn', 'owner_name', 'phone']
    ordering_fields = ['created_at', 'name', 'debt']
    ordering = ['-created_at']

    def get_permissions(self):
        """
        ИСПРАВЛЕНИЕ #2: Только STORE может создавать магазины
        ADMIN может всё
        """
        if self.action == 'create':
            return [IsAuthenticated(), IsStoreUser()]
        elif self.action in ['update', 'partial_update', 'destroy', 'approve', 'reject']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        """Фильтрация по ролям"""
        user = self.request.user
        queryset = super().get_queryset()

        if user.role == 'admin':
            return queryset
        elif user.role == 'store':
            # Магазин видит только свои магазины
            try:
                selection = StoreSelection.objects.get(user=user)
                return queryset.filter(id=selection.store.id)
            except StoreSelection.DoesNotExist:
                return queryset.none()
        else:
            # Партнёры видят только одобренные
            return queryset.filter(approval_status='approved', is_active=True)

    def perform_create(self, serializer):
        """
        ИСПРАВЛЕНИЕ #2: Создание магазина только пользователем с ролью STORE
        """
        user = self.request.user

        # Проверка роли
        if user.role != 'store':
            raise ValidationError('Только пользователи с ролью STORE могут создавать магазины')

        # Создаём магазин
        store = serializer.save(
            created_by=user,
            approval_status='pending'  # Всегда ожидает одобрения
        )

        # Автоматически выбираем этот магазин для пользователя
        StoreSelection.objects.update_or_create(
            user=user,
            defaults={'store': store}
        )

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        """Одобрить магазин"""
        store = self.get_object()
        store.approval_status = 'approved'
        store.is_active = True
        store.save()
        return Response({'status': 'approved'})

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def reject(self, request, pk=None):
        """Отклонить магазин"""
        store = self.get_object()
        store.approval_status = 'rejected'
        store.is_active = False
        store.save()
        return Response({'status': 'rejected'})

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Магазины ожидающие одобрения"""
        queryset = self.get_queryset().filter(approval_status='pending')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        ИСПРАВЛЕНИЕ #3: История магазина (запросы, бонусы, браки)
        """
        store = self.get_object()

        # Запросы магазина
        requests = StoreRequest.objects.filter(
            store=store
        ).prefetch_related('items', 'items__product').order_by('-created_at')

        # Бонусы
        bonuses = BonusHistory.objects.filter(
            store=store
        ).select_related('product', 'partner').order_by('-created_at')

        # Браки (если есть связанные партнёры)
        defects = DefectiveProduct.objects.none()
        # TODO: связать браки с магазином через заказы

        return Response({
            'requests': StoreRequestSerializer(requests, many=True).data,
            'bonuses': BonusHistorySerializer(bonuses, many=True).data,
            'defects': DefectiveProductSerializer(defects, many=True).data
        })

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Статистика по магазинам"""
        queryset = self.get_queryset()
        total_debt = queryset.aggregate(Sum('debt'))['debt__sum'] or 0
        total_stores = queryset.count()
        active_stores = queryset.filter(is_active=True).count()
        return Response({
            'total_debt': total_debt,
            'total_stores': total_stores,
            'active_stores': active_stores
        })


class StoreSelectionViewSet(viewsets.ModelViewSet):
    """
    Выбор магазина пользователем (роль STORE)
    POST/PATCH - выбрать/сменить магазин (update_or_create)
    """
    serializer_class = StoreSelectionSerializer
    permission_classes = [IsAuthenticated, IsStoreUser]

    def get_queryset(self):
        return StoreSelection.objects.filter(user=self.request.user)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Создать или обновить выбор магазина (вход в магазин)
        Использует update_or_create для поддержки OneToOneField
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        store = serializer.validated_data.get('store')

        # Проверяем что магазин одобрен
        if store.approval_status != 'approved':
            return Response(
                {'error': 'Магазин не одобрен администратором'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Создаем или обновляем выбор магазина
        selection, created = StoreSelection.objects.update_or_create(
            user=request.user,
            defaults={'store': store}
        )

        response_serializer = self.get_serializer(selection)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    def perform_update(self, serializer):
        """Обновление выбора магазина (смена магазина)"""
        store = serializer.validated_data.get('store')

        # Проверяем что магазин одобрен
        if store.approval_status != 'approved':
            raise ValidationError('Магазин не одобрен администратором')

        serializer.save(user=self.request.user)


class StoreProductRequestViewSet(viewsets.ModelViewSet):
    """
    ИСПРАВЛЕНИЕ #7: Запросы на товары магазина (временная корзина)
    """
    serializer_class = StoreProductRequestSerializer
    permission_classes = [IsAuthenticated, IsStoreUser]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return StoreProductRequest.objects.all()
        try:
            selection = StoreSelection.objects.get(user=user)
            return StoreProductRequest.objects.filter(store=selection.store)
        except StoreSelection.DoesNotExist:
            return StoreProductRequest.objects.none()

    @transaction.atomic
    def perform_create(self, serializer):
        """Создание запроса с проверкой магазина"""
        selection = StoreSelection.objects.select_for_update().get(user=self.request.user)

        if selection.store.approval_status != 'approved':
            raise ValidationError('Магазин не одобрен')

        serializer.save(store=selection.store)


class StoreRequestViewSet(viewsets.ModelViewSet):
    """
    ИСПРАВЛЕНИЕ #5-7: История запросов магазина
    Создаётся из StoreProductRequest
    """
    serializer_class = StoreRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return StoreRequest.objects.all()
        elif user.role == 'store':
            try:
                selection = StoreSelection.objects.get(user=user)
                return StoreRequest.objects.filter(store=selection.store)
            except StoreSelection.DoesNotExist:
                return StoreRequest.objects.none()
        return StoreRequest.objects.none()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        ИСПРАВЛЕНИЕ #11: Создание запроса с защитой от race condition
        """
        # Генерируем idempotency_key из данных запроса
        idempotency_key = request.data.get('idempotency_key') or str(uuid.uuid4())

        # Проверяем, не создан ли уже такой запрос
        existing = StoreRequest.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return Response(
                StoreRequestSerializer(existing).data,
                status=status.HTTP_200_OK
            )

        serializer = CreateStoreRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            selection = StoreSelection.objects.select_for_update().get(user=self.request.user)
            store = selection.store

            if store.approval_status != 'approved':
                return Response(
                    {'error': 'Магазин не одобрен'},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Создаём запрос с idempotency_key
            store_request = StoreRequestService.create_from_product_requests(
                store=store,
                user=self.request.user,
                idempotency_key=idempotency_key
            )

            return Response(
                StoreRequestSerializer(store_request).data,
                status=status.HTTP_201_CREATED
            )
        except StoreSelection.DoesNotExist:
            return Response(
                {'error': 'Магазин не выбран'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def cancel_item(self, request, pk=None):
        """Отменить позицию в запросе"""
        store_request = self.get_object()
        item_id = request.data.get('item_id')

        if not item_id:
            return Response(
                {'error': 'item_id обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )

        StoreRequestService.cancel_item(store_request, item_id)

        return Response({'status': 'cancelled'})


class StoreInventoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ИСПРАВЛЕНИЕ #9: Инвентарь магазина (только чтение)
    """
    serializer_class = StoreInventorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role == 'admin':
            return StoreInventory.objects.select_related('store', 'product')
        elif user.role == 'store':
            try:
                selection = StoreSelection.objects.get(user=user)
                return StoreInventory.objects.filter(
                    store=selection.store
                ).select_related('product')
            except StoreSelection.DoesNotExist:
                return StoreInventory.objects.none()

        return StoreInventory.objects.none()


class PartnerInventoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ИСПРАВЛЕНИЕ #9: Инвентарь партнёра (только чтение)
    """
    serializer_class = PartnerInventorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role == 'admin':
            return PartnerInventory.objects.select_related('partner', 'product')
        elif user.role == 'partner':
            return PartnerInventory.objects.filter(
                partner=user
            ).select_related('product')

        return PartnerInventory.objects.none()


class ReturnRequestViewSet(viewsets.ModelViewSet):
    """
    ИСПРАВЛЕНИЕ #8: Запросы на возврат товаров партнером к админу
    """
    serializer_class = ReturnRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['approve', 'reject']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated(), IsPartnerUser()]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return ReturnRequest.objects.all()
        return ReturnRequest.objects.filter(partner=user)

    @transaction.atomic
    def perform_create(self, serializer):
        """
        ИСПРАВЛЕНИЕ #11: Создание возврата с idempotency_key
        """
        idempotency_key = self.request.data.get('idempotency_key') or str(uuid.uuid4())

        serializer.save(
            partner=self.request.user,
            idempotency_key=idempotency_key
        )

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def approve(self, request, pk=None):
        """
        ИСПРАВЛЕНИЕ #8: Подтвердить возврат
        ИСПРАВЛЕНИЕ #16: transaction.atomic
        """
        return_request = self.get_object()

        if return_request.status != 'pending':
            return Response(
                {'error': 'Запрос уже обработан'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Списываем у партнёра и возвращаем на общий склад
        for item in return_request.items.all():
            InventoryService.remove_from_inventory(
                partner=return_request.partner,
                product=item.product,
                quantity=item.quantity
            )

            # Возвращаем на общий склад админа
            product = item.product
            product.stock_quantity += item.quantity
            product.save()

        return_request.status = 'approved'
        return_request.save()

        return Response({'status': 'approved'})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Отклонить возврат"""
        return_request = self.get_object()

        if return_request.status != 'pending':
            return Response(
                {'error': 'Запрос уже обработан'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return_request.status = 'rejected'
        return_request.save()

        return Response({'status': 'rejected'})