from rest_framework import status, generics, viewsets, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Prefetch
from django.shortcuts import get_object_or_404

from .models import Store, StoreInventory, StoreRequest, StoreRequestItem
from .serializers import (
    StoreSerializer, StoreCreateUpdateSerializer, StoreProfileSerializer,
    StoreInventorySerializer, StoreRequestSerializer, StoreRequestCreateSerializer,
    StoreRequestUpdateSerializer, ProductCatalogSerializer
)
from users.permissions import IsAdminUser, IsPartnerUser, IsStoreUser
from products.models import Product


class StoreViewSet(viewsets.ModelViewSet):
    """ViewSet для управления магазинами"""

    queryset = Store.objects.select_related('user', 'partner', 'region').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['region', 'partner', 'is_active']
    search_fields = ['store_name', 'address', 'user__name', 'user__email']
    ordering_fields = ['created_at', 'store_name']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return StoreCreateUpdateSerializer
        return StoreSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        elif self.action in ['list']:
            return [IsAdminUser() or IsPartnerUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.role == 'partner':
            # Партнёр видит только свои магазины
            qs = qs.filter(partner=user)
        elif user.role == 'store':
            # Магазин видит только себя
            qs = qs.filter(user=user)

        return qs

    @action(detail=False, methods=['get'], permission_classes=[IsStoreUser])
    def my_profile(self, request):
        """Профиль текущего магазина"""
        try:
            store = request.user.store_profile
            serializer = StoreProfileSerializer(store)
            return Response(serializer.data)
        except Store.DoesNotExist:
            return Response(
                {'error': 'Профиль магазина не найден'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['patch'], permission_classes=[IsStoreUser])
    def update_profile(self, request):
        """Обновление профиля магазина"""
        try:
            store = request.user.store_profile
            serializer = StoreProfileSerializer(store, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        except Store.DoesNotExist:
            return Response(
                {'error': 'Профиль магазина не найден'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['get'], permission_classes=[IsAdminUser])
    def inventory(self, request, pk=None):
        """Остатки товаров в магазине"""
        store = self.get_object()
        inventory = StoreInventory.objects.filter(store=store).select_related('product')
        serializer = StoreInventorySerializer(inventory, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'], permission_classes=[IsAdminUser])
    def assign_partner(self, request, pk=None):
        """Назначить партнёра магазину"""
        store = self.get_object()
        partner_id = request.data.get('partner_id')

        if not partner_id:
            return Response(
                {'error': 'partner_id обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            partner = User.objects.get(id=partner_id, role='partner')
            store.partner = partner
            store.save()

            serializer = StoreSerializer(store)
            return Response({
                'message': f'Партнёр {partner.get_full_name()} назначен магазину {store.store_name}',
                'store': serializer.data
            })

        except User.DoesNotExist:
            return Response(
                {'error': 'Партнёр не найден'},
                status=status.HTTP_404_NOT_FOUND
            )


class StoreRequestViewSet(viewsets.ModelViewSet):
    """ViewSet для запросов товаров от магазинов"""

    queryset = StoreRequest.objects.select_related('store', 'partner').prefetch_related(
        Prefetch('items', queryset=StoreRequestItem.objects.select_related('product'))
    ).all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'store', 'partner']
    ordering_fields = ['requested_at', 'processed_at']
    ordering = ['-requested_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return StoreRequestCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return StoreRequestUpdateSerializer
        return StoreRequestSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsStoreUser()]
        elif self.action in ['update', 'partial_update']:
            return [IsPartnerUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.role == 'store':
            # Магазин видит только свои запросы
            qs = qs.filter(store__user=user)
        elif user.role == 'partner':
            # Партнёр видит запросы от своих магазинов
            qs = qs.filter(partner=user)

        return qs

    @action(detail=True, methods=['patch'], permission_classes=[IsPartnerUser])
    def approve(self, request, pk=None):
        """Одобрить запрос"""
        request_obj = self.get_object()

        if request_obj.status != 'pending':
            return Response(
                {'error': 'Можно одобрить только ожидающие запросы'},
                status=status.HTTP_400_BAD_REQUEST
            )

        request_obj.approve(request.user)
        serializer = StoreRequestSerializer(request_obj)

        return Response({
            'message': 'Запрос одобрен',
            'request': serializer.data
        })

    @action(detail=True, methods=['patch'], permission_classes=[IsPartnerUser])
    def reject(self, request, pk=None):
        """Отклонить запрос"""
        request_obj = self.get_object()

        if request_obj.status != 'pending':
            return Response(
                {'error': 'Можно отклонить только ожидающие запросы'},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason', '')
        request_obj.reject(request.user, reason)
        serializer = StoreRequestSerializer(request_obj)

        return Response({
            'message': 'Запрос отклонён',
            'request': serializer.data
        })

    @action(detail=False, methods=['get'], permission_classes=[IsStoreUser])
    def my_requests(self, request):
        """Мои запросы (для магазинов)"""
        try:
            store = request.user.store_profile
            requests = self.get_queryset().filter(store=store)

            # Фильтрация по статусу
            status_filter = request.query_params.get('status')
            if status_filter:
                requests = requests.filter(status=status_filter)

            page = self.paginate_queryset(requests)
            if page is not None:
                serializer = StoreRequestSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = StoreRequestSerializer(requests, many=True)
            return Response(serializer.data)

        except Store.DoesNotExist:
            return Response(
                {'error': 'Профиль магазина не найден'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['get'], permission_classes=[IsPartnerUser])
    def partner_requests(self, request):
        """Запросы партнёра"""
        requests = self.get_queryset().filter(partner=request.user)

        # Фильтрация по статусу
        status_filter = request.query_params.get('status')
        if status_filter:
            requests = requests.filter(status=status_filter)

        page = self.paginate_queryset(requests)
        if page is not None:
            serializer = StoreRequestSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = StoreRequestSerializer(requests, many=True)
        return Response(serializer.data)


class ProductCatalogView(generics.ListAPIView):
    """Каталог товаров для магазинов"""

    queryset = Product.objects.filter(is_active=True, is_available=True).select_related('category')
    serializer_class = ProductCatalogSerializer
    permission_classes = [IsStoreUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'price', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        qs = super().get_queryset()

        # Фильтрация по партнёру (если магазин привязан к партнёру)
        try:
            store = self.request.user.store_profile
            if store.partner:
                # Здесь можно добавить логику фильтрации по товарам партнёра
                pass
        except Store.DoesNotExist:
            pass

        return qs


class StoreInventoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Остатки товаров в магазине (только чтение)"""

    queryset = StoreInventory.objects.select_related('store', 'product').all()
    serializer_class = StoreInventorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['store', 'product']
    search_fields = ['product__name']

    def get_permissions(self):
        if self.action == 'list':
            return [IsAdminUser() or IsPartnerUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.role == 'partner':
            # Партнёр видит остатки своих магазинов
            qs = qs.filter(store__partner=user)
        elif user.role == 'store':
            # Магазин видит только свои остатки
            qs = qs.filter(store__user=user)

        return qs

    @action(detail=False, methods=['get'], permission_classes=[IsStoreUser])
    def my_inventory(self, request):
        """Мои остатки (для магазина)"""
        try:
            store = request.user.store_profile
            inventory = self.get_queryset().filter(store=store)

            page = self.paginate_queryset(inventory)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(inventory, many=True)
            return Response(serializer.data)

        except Store.DoesNotExist:
            return Response(
                {'error': 'Профиль магазина не найден'},
                status=status.HTTP_404_NOT_FOUND
            )