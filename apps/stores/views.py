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
        user = self.request.user
        queryset = super().get_queryset()

        if user.role == 'admin':
            return queryset
        elif user.role == 'store':
            # UPDATE #3: Для multiple selections — фильтр по всем selected + base approved
            base_qs = queryset.filter(approval_status='approved', is_active=True)
            try:
                # NEW: Получаем все selections для user и фильтруем по их stores
                selected_stores = StoreSelection.objects.filter(user=user).values_list('store_id', flat=True)
                return base_qs | queryset.filter(id__in=selected_stores)
            except StoreSelection.DoesNotExist:
                return base_qs
        elif user.role == 'partner':
            return queryset.filter(approval_status='approved', is_active=True)
        return queryset.none()

    def perform_create(self, serializer):
        """
        UPDATE #3: Создание магазина с auto-selection (multiple allowed via create)
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

        # UPDATE: Auto-select: create новую (не update_or_create, для multiple)
        StoreSelection.objects.create(
            user=user,
            store=store
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

    @action(detail=True, methods=['post'], permission_classes=[IsStoreUser])
    def select_store(self, request, pk=None):
        """Shortcut: Выбрать магазин (создаст selection)"""
        store = self.get_object()
        if store.approval_status != 'approved':
            return Response({'error': 'Магазин не одобрен'}, status=status.HTTP_403_FORBIDDEN)

        # Создаём selection
        selection = StoreSelection.objects.create(user=request.user, store=store)
        serializer = StoreSelectionSerializer(selection)
        return Response({
            'status': 'selected',
            'selection': serializer.data
        }, status=status.HTTP_201_CREATED)

class StoreSelectionViewSet(viewsets.ModelViewSet):
    """
    Выбор магазина пользователем (роль STORE)
    NEW #3: Расширен для multiple selections, deselect, my_stores
    """
    serializer_class = StoreSelectionSerializer
    permission_classes = [IsAuthenticated, IsStoreUser]

    def get_queryset(self):
        # UPDATE: Сортировка по selected_at descending (latest first)
        return StoreSelection.objects.filter(user=self.request.user).select_related('store').order_by('-selected_at')

    def perform_create(self, serializer):
        # UPDATE: Валидация — store должен быть approved
        store = serializer.validated_data['store']
        if store.approval_status != 'approved':
            raise ValidationError({'store': 'Магазин должен быть одобрен для выбора.'})
        serializer.save(user=self.request.user)

    # NEW: Action для deselect (удаление конкретной selection)
    @action(detail=True, methods=['delete'])
    def deselect(self, request, pk=None):
        """Выйти из конкретного выбора магазина"""
        selection = self.get_object()
        selection.delete()
        return Response({'status': 'deselected'}, status=status.HTTP_204_NO_CONTENT)

    # NEW: Action для bulk deselect по store_id (если нужно)
    @action(detail=False, methods=['delete'])
    def deselect_store(self, request):
        """Выйти из магазина по ID (удалит все selections для этого store)"""
        store_id = request.data.get('store_id')
        if not store_id:
            return Response({'error': 'store_id required'}, status=status.HTTP_400_BAD_REQUEST)

        deleted_count, _ = StoreSelection.objects.filter(
            user=request.user, store_id=store_id
        ).delete()
        return Response({
            'status': 'deselected',
            'deleted_count': deleted_count
        }, status=status.HTTP_204_NO_CONTENT if deleted_count else status.HTTP_404_NOT_FOUND)

    # NEW: Helper для current store (можно вызвать в response list)
    def get_current_store(self):
        """Последний выбранный store"""
        selection = self.get_queryset().first()
        return selection.store if selection else None

    # UPDATE list: Улучшенный response с current info
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        current_store = self.get_current_store()
        return Response({
            'count': len(serializer.data),
            'selections': serializer.data,
            'current_store_id': current_store.id if current_store else None,
            'current_store_name': current_store.name if current_store else None
        })



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


class StoreRequestViewSet(viewsets.ReadOnlyModelViewSet):  # Оставляем ReadOnly, т.к. mutations через actions
    """
    Запросы магазина (wishlist -> request snapshot)
    UPDATE: Без статусов; wishlist actions; current_store integration
    """
    queryset = StoreRequest.objects.select_related('store', 'created_by').prefetch_related('items__product')
    serializer_class = StoreRequestSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['created_at']  # Убрали 'status'
    search_fields = ['store__name', 'note']
    ordering_fields = ['created_at', 'total_amount']
    ordering = ['-created_at']

    def get_permissions(self):
        """
        UPDATE: Store/ADMIN для add/remove/create; PARTNER/ADMIN видит все
        """
        if self.action in ['add_item', 'remove_item', 'create']:
            return [IsAuthenticated(), IsStoreUser()]  # Или IsAdminUser
        elif self.action == 'cancel_item':
            return [IsAuthenticated(), IsStoreUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        """
        UPDATE: Фильтрация по ролям и current_store
        """
        user = self.request.user
        queryset = super().get_queryset()

        if user.role == 'admin':
            return queryset
        elif user.role == 'store':
            current_store = self.get_current_store()
            if current_store:
                return queryset.filter(store=current_store)
            return queryset.none()
        elif user.role == 'partner':
            # UPDATE: Все requests approved stores (без status filter)
            return queryset.filter(
                store__approval_status='approved',
                store__is_active=True
            )
        return queryset.none()

    def get_current_store(self):
        """Helper: Последний выбранный store"""
        try:
            selection = StoreSelection.objects.filter(user=self.request.user).order_by('-selected_at').first()
            return selection.store if selection else None
        except (StoreSelection.DoesNotExist, AttributeError):
            return None

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        UPDATE: Snapshot wishlist в новый request с idempotency
        Тело: {"note": "опционально", "idempotency_key": "опционально"}
        """
        idempotency_key = request.data.get('idempotency_key') or str(uuid.uuid4())

        existing = StoreRequest.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return Response(
                StoreRequestSerializer(existing).data,
                status=status.HTTP_200_OK
            )

        serializer = CreateStoreRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data.get('note', '')

        store = self.get_current_store()
        if not store:
            return Response(
                {'error': 'Магазин не выбран. Выберите в /selection/'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if store.approval_status != 'approved':
            return Response(
                {'error': 'Магазин не одобрен'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            store_request = StoreRequestService.create_from_product_requests(
                store=store,
                user=self.request.user,
                note=note,
                idempotency_key=idempotency_key
            )
            return Response(
                StoreRequestSerializer(store_request).data,
                status=status.HTTP_201_CREATED
            )
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[IsStoreUser])
    def add_item(self, request):
        """
        Добавить в wishlist (StoreProductRequest)
        Тело: {"product": 1, "quantity": 5.0}
        """
        store = self.get_current_store()
        if not store:
            return Response({'error': 'Магазин не выбран'}, status=status.HTTP_400_BAD_REQUEST)

        product_id = request.data.get('product')
        quantity = Decimal(request.data.get('quantity', 0))
        if not product_id or quantity <= 0:
            return Response({'error': 'product и quantity (>0) обязательны'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            product = Product.objects.get(id=product_id)
            if product.is_weight_based and quantity < 0.1:
                raise ValidationError('Минимальное для весового: 0.1')
        except Product.DoesNotExist:
            return Response({'error': 'Товар не найден'}, status=status.HTTP_404_NOT_FOUND)

        product_request, created = StoreProductRequest.objects.update_or_create(
            store=store,
            product=product,
            defaults={'quantity': quantity}
        )

        serializer = StoreProductRequestSerializer(product_request)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response({
            'status': 'added' if created else 'updated',
            'item': serializer.data
        }, status=status_code)

    @action(detail=False, methods=['delete'], permission_classes=[IsStoreUser])
    def remove_item(self, request):
        """
        Удалить из wishlist
        Тело: {"product": 1}
        """
        store = self.get_current_store()
        if not store:
            return Response({'error': 'Магазин не выбран'}, status=status.HTTP_400_BAD_REQUEST)

        product_id = request.data.get('product')
        if not product_id:
            return Response({'error': 'product обязателен'}, status=status.HTTP_400_BAD_REQUEST)

        deleted_count, _ = StoreProductRequest.objects.filter(
            store=store, product_id=product_id
        ).delete()

        if deleted_count > 0:
            return Response({'status': 'removed', 'deleted_count': deleted_count}, status=status.HTTP_204_NO_CONTENT)
        return Response({'error': 'Товар не в wishlist'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'], permission_classes=[IsStoreUser])
    @transaction.atomic
    def cancel_item(self, request, pk=None):
        """
        Отменить item в request (существующий код)
        """
        store_request = self.get_object()
        store = self.get_current_store()

        if store_request.store != store:
            return Response({'error': 'Доступ запрещён'}, status=status.HTTP_403_FORBIDDEN)

        item_id = request.data.get('item_id')
        if not item_id:
            return Response({'error': 'item_id обязателен'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            StoreRequestService.cancel_item(store_request, item_id)
            return Response({'status': 'cancelled'})
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], permission_classes=[IsStoreUser])
    def wishlist(self, request):
        """
        Получить wishlist (StoreProductRequest)
        """
        store = self.get_current_store()
        if not store:
            return Response({'error': 'Магазин не выбран'}, status=status.HTTP_400_BAD_REQUEST)

        product_requests = store.product_requests.select_related('product').order_by('-created_at')
        serializer = StoreProductRequestSerializer(product_requests, many=True)
        total = sum(item.get('total', 0) for item in serializer.data)

        return Response({
            'store': StoreSerializer(store).data,
            'items': serializer.data,
            'total_amount': total
        })


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