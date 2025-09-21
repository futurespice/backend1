from rest_framework import serializers
from .models import Region


class RegionSerializer(serializers.ModelSerializer):
    """Базовый сериализатор региона"""

    stores_count = serializers.ReadOnlyField()
    active_orders_count = serializers.ReadOnlyField()

    class Meta:
        model = Region
        fields = [
            'id', 'name', 'code', 'description', 'is_active',
            'latitude', 'longitude', 'delivery_radius_km',
            'delivery_cost', 'priority', 'stores_count',
            'active_orders_count', 'created_at', 'updated_at'
        ]


class RegionCreateUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания/обновления региона"""

    class Meta:
        model = Region
        fields = [
            'name', 'code', 'description', 'is_active',
            'latitude', 'longitude', 'delivery_radius_km',
            'delivery_cost', 'priority'
        ]

    def validate_code(self, value):
        """Валидация кода региона"""
        value = value.upper().strip()
        if len(value) < 2:
            raise serializers.ValidationError('Код региона должен содержать минимум 2 символа')
        return value

    def validate_delivery_radius_km(self, value):
        """Валидация радиуса доставки"""
        if value < 1 or value > 200:
            raise serializers.ValidationError('Радиус доставки должен быть от 1 до 200 км')
        return value

    def validate_priority(self, value):
        """Валидация приоритета"""
        if value < 1 or value > 10:
            raise serializers.ValidationError('Приоритет должен быть от 1 до 10')
        return value


class RegionListSerializer(serializers.ModelSerializer):
    """Упрощённый сериализатор для списков"""

    class Meta:
        model = Region
        fields = ['id', 'name', 'code', 'is_active', 'stores_count']