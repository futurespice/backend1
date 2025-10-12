import django_filters
from .models import Report

class ReportFilter(django_filters.FilterSet):
    city = django_filters.NumberFilter(field_name="filter_city__id")
    partner = django_filters.NumberFilter(field_name="filter_partner__id")
    store = django_filters.NumberFilter(field_name="filter_store__id")

    class Meta:
        model = Report
        fields = ['type', 'date_from', 'date_to', 'city', 'partner', 'store']