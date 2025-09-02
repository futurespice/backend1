import django_filters
from django.contrib.auth import get_user_model
from .models import Store
from regions.models import Region, City

User = get_user_model()


class StoreFilter(django_filters.FilterSet):
    """Фильтры для магазинов"""

    # Основные фильтры
    is_active = django_filters.BooleanFilter()
    region = django_filters.ModelChoiceFilter(queryset=Region.objects.all())
    city = django_filters.ModelChoiceFilter(queryset=City.objects.all())
    owner = django_filters.ModelChoiceFilter(queryset=User.objects.filter(role='partner'))

    # Фильтр по наличию пользователя
    has_user = django_filters.BooleanFilter(method='filter_has_user')

    # Фильтр по долгам
    has_debt = django_filters.BooleanFilter(method='filter_has_debt')

    # Фильтр по дате создания
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = Store
        fields = ['is_active', 'region', 'city', 'owner', 'has_user', 'has_debt']

    def filter_has_user(self, queryset, name, value):
        """Фильтр магазинов с привязанным пользователем"""
        if value:
            return queryset.filter(user__isnull=False)
        return queryset.filter(user__isnull=True)

    def filter_has_debt(self, queryset, name, value):
        """Фильтр магазинов с долгами"""
        if value:
            # Магазины с непогашенными долгами
            return queryset.filter(debts__is_paid=False).distinct()
        return queryset.exclude(debts__is_paid=False)