from rest_framework import status, generics, viewsets, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Q

from .models import Region, DeliveryZone
from .serializers import (
    RegionSerializer, RegionTreeSerializer, RegionCreateUpdateSerializer,
    DeliveryZoneSerializer, RegionStatsSerializer
)
from apps.users.permissions import IsAdminUser


class RegionViewSet(viewsets.ModelViewSet):
    """ViewSet для управления регионами"""

    queryset = Region.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['region_type', 'parent', 'is_active']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return RegionCreateUpdateSerializer
        elif self.action == 'tree':
            return RegionTreeSerializer
        return RegionSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()

        # Фильтрация только активных регионов для не-админов
        if not (hasattr(self.request.user, 'role') and self.request.user.role == 'admin'):
            qs = qs.filter(is_active=True)

        return qs

    @action(detail=False, methods=['get'])
    def tree(self, request):
        """Получить дерево регионов"""
        # Получаем только корневые регионы (без родителя)
        root_regions = self.get_queryset().filter(parent__isnull=True)
        serializer = RegionTreeSerializer(root_regions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def countries(self, request):
        """Получить список стран"""
        countries = self.get_queryset().filter(region_type='country')
        serializer = RegionSerializer(countries, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def oblasts(self, request):
        """Получить список областей"""
        country_id = request.query_params.get('country')
        oblasts = self.get_queryset().filter(region_type='oblast')

        if country_id:
            oblasts = oblasts.filter(parent_id=country_id)

        serializer = RegionSerializer(oblasts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def cities(self, request):
        """Получить список городов"""
        oblast_id = request.query_params.get('oblast')
        district_id = request.query_params.get('district')

        cities = self.get_queryset().filter(region_type__in=['city', 'village'])

        if oblast_id:
            cities = cities.filter(parent_id=oblast_id)
        elif district_id:
            cities = cities.filter(parent_id=district_id)

        serializer = RegionSerializer(cities, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def children(self, request, pk=None):
        """Получить дочерние регионы"""
        region = self.get_object()
        children = region.children.filter(is_active=True)
        serializer = RegionSerializer(children, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Статистика по региону"""
        region = self.get_object()

        # Получаем все дочерние регионы рекурсивно
        all_children = region.get_all_children()
        region_ids = [region.id] + [child.id for child in all_children]

        # Подсчитываем статистику
        from apps.stores.models import Store

        stores = Store.objects.filter(region_id__in=region_ids)
        total_stores = stores.count()
        active_stores = stores.filter(is_active=True).count()

        partners = stores.filter(partner__isnull=False).values('partner').distinct()
        total_partners = partners.count()

        # Статистика заказов (будет добавлена позже)
        total_orders = 0
        total_revenue = 0
        avg_order_value = 0

        stats_data = {
            'region': region,
            'total_stores': total_stores,
            'active_stores': active_stores,
            'total_partners': total_partners,
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'avg_order_value': avg_order_value,
        }

        serializer = RegionStatsSerializer(stats_data)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def stores(self, request, pk=None):
        """Магазины в регионе"""
        region = self.get_object()

        # Получаем все дочерние регионы
        all_children = region.get_all_children()
        region_ids = [region.id] + [child.id for child in all_children]

        from apps.stores.models import Store
        from apps.stores.serializers import StoreSerializer

        stores = Store.objects.filter(
            region_id__in=region_ids,
            is_active=True
        ).select_related('user', 'partner', 'region')

        page = self.paginate_queryset(stores)
        if page is not None:
            serializer = StoreSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = StoreSerializer(stores, many=True)
        return Response(serializer.data)


class DeliveryZoneViewSet(viewsets.ModelViewSet):
    """ViewSet для управления зонами доставки"""

    queryset = DeliveryZone.objects.select_related('region').all()
    serializer_class = DeliveryZoneSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['region', 'is_active']
    search_fields = ['name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()

        # Только активные зоны для не-админов
        if not (hasattr(self.request.user, 'role') and self.request.user.role == 'admin'):
            qs = qs.filter(is_active=True)

        return qs

    @action(detail=False, methods=['post'])
    def check_delivery(self, request):
        """Проверить возможность доставки в точку"""
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')

        if not latitude or not longitude:
            return Response(
                {'error': 'Необходимо указать latitude и longitude'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (ValueError, TypeError):
            return Response(
                {'error': 'Некорректные координаты'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Ищем подходящие зоны доставки
        suitable_zones = []

        for zone in self.get_queryset():
            if zone.is_point_in_zone(latitude, longitude):
                suitable_zones.append(zone)

        if suitable_zones:
            serializer = DeliveryZoneSerializer(suitable_zones, many=True)
            return Response({
                'delivery_available': True,
                'zones': serializer.data
            })
        else:
            return Response({
                'delivery_available': False,
                'message': 'Доставка в указанную точку недоступна'
            })


class RegionListView(generics.ListAPIView):
    """Простой список регионов для селектов"""

    queryset = Region.objects.filter(is_active=True)
    serializer_class = RegionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['region_type', 'parent']
    search_fields = ['name']
    pagination_class = None  # Отключаем пагинацию

    def get_queryset(self):
        qs = super().get_queryset()

        # Фильтрация по типу региона
        region_type = self.request.query_params.get('type')
        if region_type:
            qs = qs.filter(region_type=region_type)

        # Фильтрация по родительскому региону
        parent_id = self.request.query_params.get('parent')
        if parent_id:
            qs = qs.filter(parent_id=parent_id)

        return qs.order_by('name')