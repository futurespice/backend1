import django_filters
from .models import Report

class ReportFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    city = django_filters.NumberFilter(field_name='data__city')  # Пример, если в data есть city
    partner = django_filters.NumberFilter(field_name='generated_by__id')
    store = django_filters.NumberFilter(field_name='data__store')

    class Meta:
        model = Report
        fields = ['type', 'generated_by']