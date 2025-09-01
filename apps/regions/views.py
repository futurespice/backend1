from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend

from .models import Region, City
from .serializers import (
    RegionSerializer, RegionWithCitiesSerializer, RegionCreateSerializer,
    CitySerializer, CityCreateSerializer
)
from users.permissions import IsAdminUser


class RegionViewSet(viewsets.ModelViewSet):
    """API регионов"""
    queryset = Region.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'create':
            return RegionCreateSerializer
        elif self.action == 'retrieve':
            return RegionWithCitiesSerializer
        return RegionSerializer

    def get_permissions(self):
        """Только админы могут создавать/редактировать/удалять"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsAdminUser]
        else:
            permission_classes = [permissions.IsAuthenticated]

        return [permission() for permission in permission_classes]

    @action(detail=True, methods=['get'])
    def cities(self, request, pk=None):
        """Получить города региона"""
        region = self.get_object()
        cities = region.cities.all().order_by('name')
        serializer = CitySerializer(cities, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def add_city(self, request, pk=None):
        """Добавить город в регион"""
        region = self.get_object()

        data = request.data.copy()
        data['region'] = region.id

        serializer = CityCreateSerializer(data=data)
        if serializer.is_valid():
            city = serializer.save()
            return Response(
                CitySerializer(city).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CityViewSet(viewsets.ModelViewSet):
    """API городов"""
    queryset = City.objects.select_related('region').all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['region']
    search_fields = ['name', 'region__name']
    ordering = ['region__name', 'name']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CityCreateSerializer
        return CitySerializer

    def get_permissions(self):
        """Только админы могут создавать/редактировать/удалять"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsAdminUser]
        else:
            permission_classes = [permissions.IsAuthenticated]

        return [permission() for permission in permission_classes]

    @action(detail=False, methods=['get'])
    def by_region(self, request):
        """Получить города, сгруппированные по регионам"""
        regions = Region.objects.prefetch_related('cities').all().order_by('name')

        result = []
        for region in regions:
            cities = region.cities.all().order_by('name')
            result.append({
                'region': RegionSerializer(region).data,
                'cities': CitySerializer(cities, many=True).data
            })

        return Response(result)