from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Q

from .models import Region
from .serializers import (
    RegionSerializer,
    RegionCreateUpdateSerializer,
    RegionListSerializer
)
from users.permissions import IsAdminUser, IsPartnerUser


class RegionViewSet(viewsets.ModelViewSet):
    """ViewSet для управления регионами"""

    queryset = Region.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'priority']
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'code', 'priority', 'created_at']
    ordering = ['priority', 'name']

    def get_serializer_class(self):
        if self.action == 'list':
            return RegionListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return RegionCreateUpdateSerializer
        return RegionSerializer

    def get_permissions(self):
        """Права доступа по действиям"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        elif self.action in ['list', 'retrieve']:
            return [IsPartnerUser() or IsAdminUser()]
        return super().get_permissions()

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Список только активных регионов"""
        active_regions = self.get_queryset().filter(is_active=True)
        serializer = RegionListSerializer(active_regions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Статистика по региону"""
        region = self.get_object()

        # Получаем статистику через related_name (когда добавим stores)
        stats = {
            'region_info': {
                'id': region.id,
                'name': region.name,
                'code': region.code
            },
            'stores_count': region.stores_count,
            'active_orders_count': region.active_orders_count,
            'delivery_settings': {
                'radius_km': region.delivery_radius_km,
                'cost': float(region.delivery_cost),
                'priority': region.priority
            }
        }

        return Response(stats)

    @action(detail=False, methods=['get'])
    def map_data(self, request):
        """Данные для отображения регионов на карте"""
        regions = self.get_queryset().filter(
            is_active=True,
            latitude__isnull=False,
            longitude__isnull=False
        )

        map_data = []
        for region in regions:
            map_data.append({
                'id': region.id,
                'name': region.name,
                'code': region.code,
                'latitude': float(region.latitude),
                'longitude': float(region.longitude),
                'delivery_radius_km': region.delivery_radius_km,
                'stores_count': region.stores_count,
                'priority': region.priority
            })

        return Response(map_data)