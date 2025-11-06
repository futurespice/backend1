import django_filters
from .models import PartnerOrder, StoreOrder, OrderReturn


class PartnerOrderFilter(django_filters.FilterSet):
    """Фильтры для заказов партнёров"""
    status = django_filters.ChoiceFilter(choices=PartnerOrder._meta.get_field('status').choices)
    created_at_from = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    created_at_to = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    partner = django_filters.NumberFilter(field_name='partner__id')

    class Meta:
        model = PartnerOrder
        fields = ['status', 'partner']


class StoreOrderFilter(django_filters.FilterSet):
    """Фильтры для заказов магазинов"""
    is_fulfilled = django_filters.BooleanFilter()
    created_at_from = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    created_at_to = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    store = django_filters.NumberFilter(field_name='store__id')
    partner = django_filters.NumberFilter(field_name='partner__id')

    class Meta:
        model = StoreOrder
        fields = ['is_fulfilled', 'store', 'partner']


class OrderReturnFilter(django_filters.FilterSet):
    """Фильтры для возвратов"""
    status = django_filters.ChoiceFilter(choices=OrderReturn._meta.get_field('status').choices)
    created_at_from = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    created_at_to = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    order = django_filters.NumberFilter(field_name='order__id')

    class Meta:
        model = OrderReturn
        fields = ['status', 'order']