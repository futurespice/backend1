from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Store
from regions.models import Region, City

User = get_user_model()

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Store

User = get_user_model()


class StoreListSerializer(serializers.ModelSerializer):
    """Список магазинов"""
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True)
    city_name = serializers.CharField(source='city.name', read_only=True)
    debt_amount = serializers.SerializerMethodField()
    total_orders = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            'id', 'name', 'inn', 'phone', 'contact_name',
            'owner_name', 'region_name', 'city_name', 'address',
            'is_active', 'debt_amount', 'total_orders', 'created_at'
        ]

    def get_debt_amount(self, obj):
        return obj.get_debt_amount()

    def get_total_orders(self, obj):
        return obj.get_total_orders_count()


class StoreDetailSerializer(serializers.ModelSerializer):
    """Подробная информация о магазине"""
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    owner_phone = serializers.CharField(source='owner.phone', read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True)
    city_name = serializers.CharField(source='city.name', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    debt_amount = serializers.SerializerMethodField()
    total_orders = serializers.SerializerMethodField()
    total_orders_amount = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            'id', 'name', 'inn', 'phone', 'contact_name',
            'owner', 'owner_name', 'owner_phone',
            'user', 'user_name',
            'region', 'region_name', 'city', 'city_name', 'address',
            'is_active', 'debt_amount', 'total_orders', 'total_orders_amount',
            'created_at', 'updated_at'
        ]

    def get_debt_amount(self, obj):
        return obj.get_debt_amount()

    def get_total_orders(self, obj):
        return obj.get_total_orders_count()

    def get_total_orders_amount(self, obj):
        return obj.get_total_orders_amount()


class StoreCreateUpdateSerializer(serializers.ModelSerializer):
    """Создание и обновление магазина"""

    class Meta:
        model = Store
        fields = [
            'name', 'inn', 'phone', 'contact_name',
            'region', 'city', 'address', 'is_active'
        ]

    def validate_inn(self, value):
        # Проверяем уникальность ИНН при создании
        if self.instance is None:  # Создание
            if Store.objects.filter(inn=value).exists():
                raise serializers.ValidationError("Магазин с таким ИНН уже существует")
        else:  # Обновление
            if Store.objects.filter(inn=value).exclude(pk=self.instance.pk).exists():
                raise serializers.ValidationError("Магазин с таким ИНН уже существует")
        return value

    def validate_phone(self, value):
        # Проверяем уникальность телефона
        if self.instance is None:  # Создание
            if Store.objects.filter(phone=value).exists():
                raise serializers.ValidationError("Магазин с таким телефоном уже существует")
        else:  # Обновление
            if Store.objects.filter(phone=value).exclude(pk=self.instance.pk).exists():
                raise serializers.ValidationError("Магазин с таким телефоном уже существует")
        return value

    def validate(self, attrs):
        # Проверяем, что город принадлежит выбранному региону
        if 'region' in attrs and 'city' in attrs:
            if attrs['city'].region != attrs['region']:
                raise serializers.ValidationError("Выбранный город не принадлежит указанному региону")
        return attrs

    def create(self, validated_data):
        # Автоматически назначаем владельца
        if self.context['request'].user.role == 'partner':
            validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)


class StoreAssignUserSerializer(serializers.Serializer):
    """Назначение пользователя магазину"""
    user_id = serializers.IntegerField()

    def validate_user_id(self, value):
        try:
            user = User.objects.get(id=value, role='store', is_approved=True)
            # Проверяем, что пользователь еще не привязан к магазину
            if hasattr(user, 'store'):
                raise serializers.ValidationError("Этот пользователь уже привязан к другому магазину")
            return value
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь не найден или не является магазином")


class StoreStatisticsSerializer(serializers.Serializer):
    """Статистика магазина"""
    store_id = serializers.IntegerField()
    store_name = serializers.CharField()

    # Заказы
    total_orders = serializers.IntegerField()
    total_orders_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    avg_order_amount = serializers.DecimalField(max_digits=12, decimal_places=2)

    # Долги
    total_debt = serializers.DecimalField(max_digits=15, decimal_places=2)
    unpaid_debt = serializers.DecimalField(max_digits=15, decimal_places=2)

    # Бонусы
    bonus_items_received = serializers.IntegerField()
    bonus_amount_saved = serializers.DecimalField(max_digits=12, decimal_places=2)

    # Периоды
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()




class RegionSerializer(serializers.ModelSerializer):
    cities_count = serializers.SerializerMethodField()

    class Meta:
        model = Region
        fields = ['id', 'name', 'cities_count', 'created_at']

    def get_cities_count(self, obj):
        return obj.cities.count()


class CitySerializer(serializers.ModelSerializer):
    region_name = serializers.CharField(source='region.name', read_only=True)

    class Meta:
        model = City
        fields = ['id', 'name', 'region', 'region_name', 'created_at']