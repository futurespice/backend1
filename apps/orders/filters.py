import django_filters
from .models import Order

class OrderFilter(django_filters.FilterSet):
    total_min = django_filters.NumberFilter(field_name="total_amount", lookup_expr='gte')
    total_max = django_filters.NumberFilter(field_name="total_amount", lookup_expr='lte')
    city = django_filters.NumberFilter(field_name="store__city__id")
    region = django_filters.NumberFilter(field_name="store__region__id")
    partner = django_filters.NumberFilter(field_name="partner__id")
    store_inn = django_filters.CharFilter(field_name="store__inn", lookup_expr='exact')

    class Meta:
        model = Order
        fields = ['store', 'partner', 'status', 'total_min', 'total_max', 'city', 'region', 'store_inn']