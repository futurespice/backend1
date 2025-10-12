import django_filters
from .models import Store


class StoreFilter(django_filters.FilterSet):
    debt_min = django_filters.NumberFilter(field_name="debt", lookup_expr='gte')
    debt_max = django_filters.NumberFilter(field_name="debt", lookup_expr='lte')

    class Meta:
        model = Store
        fields = ['region', 'city', 'is_active', 'debt_min', 'debt_max']