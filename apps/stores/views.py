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

from products.serializers import BonusHistorySerializer, DefectiveProductSerializer
from .models import (
    Region, City, Store, StoreSelection,
    StoreProductRequest, StoreRequest, StoreRequestItem,
    StoreInventory, PartnerInventory, ReturnRequest, ReturnRequestItem
)
from .serializers import (
    RegionSerializer, StoreSerializer, StoreSelectionSerializer,
    StoreProductRequestSerializer, CreateStoreRequestSerializer,
    StoreRequestSerializer, StoreInventorySerializer,
    PartnerInventorySerializer, ReturnRequestSerializer
)
from .services import StoreRequestService, InventoryService
from users.permissions import IsAdminUser, IsPartnerUser, IsStoreUser
from products.models import Product, BonusHistory, DefectiveProduct
from .filters import StoreFilter


class RegionViewSet(viewsets.ReadOnlyModelViewSet):
    """Регионы и города"""
    queryset = Region.objects.all().prefetch_related('cities')
    serializer_class = RegionSerializer
    permission_classes = [IsAuthenticated]


class StoreViewSet(viewsets.ModelViewSet):
    """
    Магазины (CRUD)
    - GET /stores/ - список магазинов (все роли)
    - POST /stores/ - создать магазин (ADMIN, STORE)
    - GET /stores/{id}/ - детали магазина
    - PATCH /stores/{id}/ - обновить магазин (ADMIN)
    - DELETE /stores/{id}/ - удалить магазин (ADMIN)
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
        """ADMIN и STORE могут создавать магазины"""
        if self.action == 'create':
            return [IsAuthenticated()]
        elif self.action in ['update', 'partial_update', 'destroy', 'approve', 'reject', 'freeze', 'unfreeze', 'repay_debt']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        """Создание магазина с pending статусом"""
        serializer.save(created_by=self.request.user, approval_status='pending')

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Одобрить магазин"""
        store = self.get_object()
        store.approval_status = 'approved'
        store.is_active = True
        store.save()
        return Response({'status': 'approved'})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Отклонить магазин"""
        store = self.get_object()
        store.approval_status = 'rejected'
        store.is_active = False
        store.save()
        return Response({'status': 'rejected'})

    @action(detail=True, methods=['post'])
    def freeze(self, request, pk=None):
        """Заморозить магазин"""
        store = self.get_object()
        store.is_active = False
        store.save()
        return Response({'status': 'frozen'})

    @action(detail=True, methods=['post'])
    def unfreeze(self, request, pk=None):
        """Разморозить магазин"""
        store = self.get_object()
        store.is_active = True
        store.save()
        return Response({'status': 'unfrozen'})

    @action(detail=True, methods=['post'])
    def repay_debt(self, request, pk=None):
        """Погасить долг магазина"""
        store = self.get_object()
        amount = Decimal(request.data.get('amount', 0))
        if amount <= 0 or amount > store.debt:
            return Response({'error': 'Недопустимая сумма'}, status=status.HTTP_400_BAD_REQUEST)
        store.debt -= amount
        store.save()
        return Response({'status': 'debt_updated', 'new_debt': store.debt})

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """История заказов, бонусов и брака"""
        store = self.get_object()
        requests = StoreRequest.objects.filter(store=store).select_related('created_by')
        bonuses = BonusHistory.objects.filter(store=store).select_related('product', 'partner')
        defects = DefectiveProduct.objects.filter(partner__in=StoreSelection.objects.filter(store=store).values('user')).select_related('product')

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

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return Store.objects.all()
        elif user.role == 'store':
            try:
                selection = StoreSelection.objects.get(user=user)
                return Store.objects.filter(id=selection.store.id)
            except StoreSelection.DoesNotExist:
                return Store.objects.none()
        return Store.objects.filter(approval_status='approved', is_active=True)


class StoreSelectionViewSet(viewsets.ModelViewSet):
    """
    Выбор магазина пользователем (роль STORE)
    - GET /selection/ - текущий выбор
    - POST /selection/ - выбрать магазин
    """
    serializer_class = StoreSelectionSerializer
    permission_classes = [IsAuthenticated, IsStoreUser]

    def get_queryset(self):
        return StoreSelection.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class StoreProductRequestViewSet(viewsets.ModelViewSet):
    """
    Запросы на товары магазина (без влияния на инвентарь)
    - GET /product-requests/ - список запросов
    - POST /product-requests/ - создать запрос
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

    def perform_create(self, serializer):
        selection = StoreSelection.objects.get(user=self.request.user)
        serializer.save(store=selection.store)


class StoreRequestViewSet(viewsets.ModelViewSet):
    """
    История запросов магазина
    - GET /requests/ - список запросов
    - POST /requests/ - создать запрос
    - POST /requests/{id}/approve/ - подтвердить
    - POST /requests/{id}/reject/ - отклонить
    - POST /requests/{id}/cancel-item/ - отменить позицию
    """
    serializer_class = StoreRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['approve', 'reject']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]

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

    def create(self, request, *args, **kwargs):
        serializer = CreateStoreRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            selection = StoreSelection.objects.get(user=self.request.user)
            store = selection.store
            if store.approval_status != 'approved':
                return Response({'error': 'Магазин не одобрен'}, status=status.HTTP_403_FORBIDDEN)
            request_obj = StoreRequestService.create_request(
                store=store,
                created_by=self.request.user,
                items_data=serializer.validated_data['items'],
                note=serializer.validated_data.get('note', '')
            )
            return Response(StoreRequestSerializer(request_obj).data, status=status.HTTP_201_CREATED)
        except StoreSelection.DoesNotExist:
            return Response({'error': 'Магазин не выбран'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def approve(self, request, pk=None):
        """Подтвердить запрос"""
        store_request = self.get_object()
        if store_request.status != 'pending':
            return Response({'error': 'Запрос уже обработан'}, status=status.HTTP_400_BAD_REQUEST)

        for item in store_request.items.filter(is_cancelled=False):
            InventoryService.transfer_to_store(
                partner=store_request.created_by,
                store=store_request.store,
                product=item.product,
                quantity=item.quantity
            )

        store_request.status = 'approved'
        store_request.save()
        return Response({'status': 'approved'})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Отклонить запрос"""
        store_request = self.get_object()
        if store_request.status != 'pending':
            return Response({'error': 'Запрос уже обработан'}, status=status.HTTP_400_BAD_REQUEST)
        store_request.status = 'rejected'
        store_request.save()
        return Response({'status': 'rejected'})

    @action(detail=True, methods=['post'])
    def cancel_item(self, request, pk=None):
        """Отменить позицию в запросе"""
        store_request = self.get_object()
        item_id = request.data.get('item_id')
        try:
            item = store_request.items.get(id=item_id)
            StoreRequestService.cancel_item(item)
            return Response(StoreRequestSerializer(store_request).data)
        except StoreRequestItem.DoesNotExist:
            return Response({'error': 'Позиция не найдена'}, status=status.HTTP_404_NOT_FOUND)


class StoreInventoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Инвентарь магазина
    - GET /inventory/ - список товаров
    - GET /inventory/?store={id} - фильтр по магазину
    """
    serializer_class = StoreInventorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['store', 'product']
    search_fields = ['product__name']
    ordering_fields = ['quantity', 'last_updated']
    ordering = ['-last_updated']

    def get_queryset(self):
        """Фильтрация по роли"""
        user = self.request.user
        if user.role == 'admin':
            return StoreInventory.objects.select_related('store', 'product').filter(quantity__gt=0)
        elif user.role == 'partner':
            return StoreInventory.objects.select_related('store', 'product').filter(quantity__gt=0)
        elif user.role == 'store':
            try:
                selection = StoreSelection.objects.get(user=user)
                return StoreInventory.objects.filter(
                    store=selection.store,
                    quantity__gt=0
                ).select_related('product')
            except StoreSelection.DoesNotExist:
                return StoreInventory.objects.none()
        return StoreInventory.objects.none()


class PartnerInventoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Инвентарь партнёра (личный склад партнёра)
    - GET /partner-inventory/ - список товаров партнёра
    """
    serializer_class = PartnerInventorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['product']
    search_fields = ['product__name']
    ordering_fields = ['quantity', 'last_updated']
    ordering = ['-last_updated']

    def get_queryset(self):
        """Фильтрация по роли"""
        user = self.request.user
        if user.role == 'admin':
            return PartnerInventory.objects.select_related('partner', 'product').filter(quantity__gt=0)
        elif user.role == 'partner':
            return PartnerInventory.objects.filter(
                partner=user,
                quantity__gt=0
            ).select_related('product')
        return PartnerInventory.objects.none()


class ReturnRequestViewSet(viewsets.ModelViewSet):
    """
    Запросы на возврат товаров партнером
    - GET /returns/ - список возвратов
    - POST /returns/ - создать возврат
    - POST /returns/{id}/approve/ - подтвердить
    - POST /returns/{id}/reject/ - отклонить
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

    def perform_create(self, serializer):
        serializer.save(partner=self.request.user)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def approve(self, request, pk=None):
        """Подтвердить возврат"""
        return_request = self.get_object()
        if return_request.status != 'pending':
            return Response({'error': 'Запрос уже обработан'}, status=status.HTTP_400_BAD_REQUEST)

        for item in return_request.items.all():
            InventoryService.remove_from_inventory(
                partner=return_request.partner,
                product=item.product,
                quantity=item.quantity
            )
            # Возвращаем на общий склад (products.Product)
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
            return Response({'error': 'Запрос уже обработан'}, status=status.HTTP_400_BAD_REQUEST)
        return_request.status = 'rejected'
        return_request.save()
        return Response({'status': 'rejected'})