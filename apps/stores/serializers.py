# apps/stores/serializers.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
from rest_framework import serializers
from decimal import Decimal
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from .models import (
    Region, City, Store, StoreSelection,
    StoreProductRequest, StoreRequest, StoreRequestItem,
    StoreInventory, PartnerInventory, ReturnRequest, ReturnRequestItem
)
from products.models import Product


# ============= REGION & CITY =============

class CitySerializer(serializers.ModelSerializer):
    """ИСПРАВЛЕНИЕ #4: Сериализатор города"""
    region_name = serializers.CharField(source='region.name', read_only=True)

    class Meta:
        model = City
        fields = ['id', 'name', 'region', 'region_name']


class RegionSerializer(serializers.ModelSerializer):
    """ИСПРАВЛЕНИЕ #4: Сериализатор региона с городами"""
    cities = CitySerializer(many=True, read_only=True)

    class Meta:
        model = Region
        fields = ['id', 'name', 'cities']


# ============= STORE =============

class StoreSerializer(serializers.ModelSerializer):
    """Сериализатор магазина"""
    region_name = serializers.CharField(source='region.name', read_only=True)
    city_name = serializers.CharField(source='city.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    approval_status_display = serializers.CharField(source='get_approval_status_display', read_only=True)

    class Meta:
        model = Store
        fields = [
            'id', 'name', 'inn', 'owner_name', 'phone',
            'region', 'region_name', 'city', 'city_name',
            'address', 'latitude', 'longitude',
            'debt', 'approval_status', 'approval_status_display',
            'is_active', 'created_by', 'created_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['debt', 'created_by', 'created_at', 'updated_at']

    def validate(self, data):
        """
        Валидация: город должен принадлежать выбранному региону
        """
        region = data.get('region')
        city = data.get('city')

        # Проверяем только если оба поля присутствуют
        if region and city:
            # Проверяем что город принадлежит выбранному региону
            if city.region_id != region.id:
                raise serializers.ValidationError({
                    'city': f'Город {city.name} не принадлежит региону {region.name}. '
                            f'Этот город находится в регионе {city.region.name}.'
                })

        return data


class StoreSelectionSerializer(serializers.ModelSerializer):
    """Выбор магазина"""
    store_name = serializers.CharField(source='store.name', read_only=True)

    class Meta:
        model = StoreSelection
        fields = ['id', 'store', 'store_name', 'selected_at']


# ============= PRODUCT REQUESTS =============

class StoreProductRequestSerializer(serializers.ModelSerializer):
    """Запрос на товар (временная корзина)"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(
        source='product.price',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    # ИСПРАВЛЕНИЕ #19: типизация для @extend_schema_field
    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total(self, obj) -> Decimal:
        """Общая стоимость"""
        return obj.quantity * obj.product.price

    total = serializers.SerializerMethodField()

    class Meta:
        model = StoreProductRequest
        fields = [
            'id', 'store', 'product', 'product_name',
            'product_price', 'quantity', 'total',
            'created_at'
        ]
        read_only_fields = ['store', 'created_at']


# ============= STORE REQUESTS =============

class StoreRequestItemSerializer(serializers.ModelSerializer):
    """Позиция в запросе магазина"""
    product_name = serializers.CharField(source='product.name', read_only=True)

    # ИСПРАВЛЕНИЕ #19: типизация
    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total(self, obj) -> Decimal:
        """Общая стоимость позиции"""
        return obj.total

    total = serializers.SerializerMethodField()

    class Meta:
        model = StoreRequestItem
        fields = [
            'id', 'product', 'product_name',
            'quantity', 'price', 'total', 'is_cancelled'
        ]


class StoreRequestSerializer(serializers.ModelSerializer):
    """История запросов магазина"""
    store_name = serializers.CharField(source='store.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    items = StoreRequestItemSerializer(many=True, read_only=True)

    class Meta:
        model = StoreRequest
        fields = [
            'id', 'store', 'store_name', 'created_by', 'created_by_name',
            'total_amount', 'note', 'items', 'created_at'
        ]
        read_only_fields = ['total_amount', 'created_at']


class CreateStoreRequestSerializer(serializers.Serializer):
    """
    ИСПРАВЛЕНИЕ #11: Создание запроса с idempotency_key
    """
    note = serializers.CharField(required=False, allow_blank=True)
    idempotency_key = serializers.CharField(required=False, allow_null=True)


# ============= INVENTORY =============

class StoreInventorySerializer(serializers.ModelSerializer):
    """ИСПРАВЛЕНИЕ #9: Инвентарь магазина"""
    store_name = serializers.CharField(source='store.name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.get_unit_display', read_only=True)

    # ИСПРАВЛЕНИЕ #19: типизация
    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total_price(self, obj) -> Decimal:
        """Общая стоимость"""
        return obj.total_price

    total_price = serializers.SerializerMethodField()

    class Meta:
        model = StoreInventory
        fields = [
            'id', 'store', 'store_name', 'product', 'product_name',
            'product_unit', 'quantity', 'total_price', 'last_updated'
        ]


class PartnerInventorySerializer(serializers.ModelSerializer):
    """ИСПРАВЛЕНИЕ #9: Инвентарь партнёра"""
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.get_unit_display', read_only=True)

    class Meta:
        model = PartnerInventory
        fields = [
            'id', 'partner', 'partner_name', 'product', 'product_name',
            'product_unit', 'quantity', 'last_updated'
        ]


# ============= RETURN REQUESTS =============

class ReturnRequestItemSerializer(serializers.ModelSerializer):
    """Позиция в возврате"""
    product_name = serializers.CharField(source='product.name', read_only=True)

    # ИСПРАВЛЕНИЕ #19: типизация
    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total(self, obj) -> Decimal:
        """Общая стоимость позиции"""
        return obj.total

    total = serializers.SerializerMethodField()

    class Meta:
        model = ReturnRequestItem
        fields = [
            'id', 'product', 'product_name',
            'quantity', 'price', 'total'
        ]


class ReturnRequestSerializer(serializers.ModelSerializer):
    """ИСПРАВЛЕНИЕ #8: Запрос на возврат"""
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    store_name = serializers.CharField(source='store.name', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items = ReturnRequestItemSerializer(many=True, read_only=True)

    class Meta:
        model = ReturnRequest
        fields = [
            'id', 'partner', 'partner_name', 'store', 'store_name',
            'order', 'status', 'status_display', 'total_amount',
            'reason', 'items', 'created_at'
        ]
        read_only_fields = ['partner', 'total_amount', 'status', 'created_at']