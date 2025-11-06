from rest_framework import serializers
from decimal import Decimal
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from .models import (
    PartnerOrder, PartnerOrderItem,
    StoreOrder, StoreOrderItem,
    OrderHistory, OrderReturn, OrderReturnItem
)
from products.models import Product
from stores.models import Store


# ============= PARTNER ORDER (партнёр → админ) =============

class PartnerOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total(self, obj) -> Decimal:
        return obj.total

    total = serializers.SerializerMethodField()

    class Meta:
        model = PartnerOrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'price', 'total']


class PartnerOrderSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items = PartnerOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = PartnerOrder
        fields = [
            'id', 'partner', 'partner_name', 'status', 'status_display',
            'total_amount', 'note', 'items',
            'idempotency_key', 'created_at', 'updated_at'
        ]
        read_only_fields = ['partner', 'total_amount', 'idempotency_key', 'created_at', 'updated_at']


class CreatePartnerOrderSerializer(serializers.Serializer):
    """Создание заказа партнёра"""
    note = serializers.CharField(max_length=500, allow_blank=True, required=False)
    items = serializers.ListField(child=serializers.DictField())
    idempotency_key = serializers.CharField(max_length=100, required=False)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Необходимо указать хотя бы одну позицию")
        for item in value:
            if 'product' not in item or 'quantity' not in item:
                raise serializers.ValidationError("Каждая позиция должна содержать product и quantity")
        return value


# ============= STORE ORDER (магазин → партнёр) =============

class StoreOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total(self, obj) -> Decimal:
        return obj.total

    total = serializers.SerializerMethodField()

    class Meta:
        model = StoreOrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'price', 'is_bonus', 'total']


class StoreOrderSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='store.name', read_only=True)
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    items = StoreOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = StoreOrder
        fields = [
            'id', 'store', 'store_name', 'partner', 'partner_name',
            'store_request', 'is_fulfilled', 'total_amount', 'bonus_applied',
            'note', 'items', 'idempotency_key', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'store', 'partner', 'store_request', 'total_amount', 'bonus_applied',
            'idempotency_key', 'created_at', 'updated_at'
        ]


class CreateStoreOrderSerializer(serializers.Serializer):
    """Создание заказа магазина из StoreRequest"""
    store_request_id = serializers.IntegerField()
    note = serializers.CharField(max_length=500, allow_blank=True, required=False)
    idempotency_key = serializers.CharField(max_length=100, required=False)


# ============= ORDER HISTORY =============

class OrderHistorySerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True, allow_null=True)

    class Meta:
        model = OrderHistory
        fields = [
            'id', 'order_type', 'order_id', 'type', 'type_display',
            'product', 'product_name', 'amount', 'quantity',
            'note', 'created_at'
        ]


# ============= ORDER RETURNS =============

class OrderReturnItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total(self, obj) -> Decimal:
        return obj.total

    total = serializers.SerializerMethodField()

    class Meta:
        model = OrderReturnItem
        fields = ['id', 'product', 'product_name', 'quantity', 'price', 'total']


class OrderReturnSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source='order.id', read_only=True)
    store_name = serializers.CharField(source='order.store.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items = OrderReturnItemSerializer(many=True, read_only=True)

    class Meta:
        model = OrderReturn
        fields = [
            'id', 'order', 'order_id', 'store_name', 'status', 'status_display',
            'total_amount', 'reason', 'items',
            'idempotency_key', 'created_at', 'updated_at'
        ]
        read_only_fields = ['total_amount', 'idempotency_key', 'created_at', 'updated_at']


class CreateOrderReturnSerializer(serializers.Serializer):
    """Создание возврата"""
    order_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=500)
    items = serializers.ListField(child=serializers.DictField())
    idempotency_key = serializers.CharField(max_length=100, required=False)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Необходимо указать хотя бы одну позицию")
        for item in value:
            if 'product' not in item or 'quantity' not in item:
                raise serializers.ValidationError("Каждая позиция должна содержать product и quantity")
        return value